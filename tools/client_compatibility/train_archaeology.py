"""Fine-tune only Laya's decision head on frozen synthetic telescope examples."""
import argparse
import json
from pathlib import Path
import random
import subprocess
import time
import torch
from safetensors.torch import save_file
from laya.common import build_sequence,collate_items,QTYPES
from . import lab_runtime as lab
from . import archaeology_policy as policy


def encode(agent,rows):
    result=[]
    for row in rows:
        q=agent._to_internal(row['question'])
        ids,markers=build_sequence(agent.tok,row['state'],q,agent.cfg['max_len'],agent.cfg['head_max_len'])
        if len(markers)!=len(q['crit']):raise ValueError('options truncated')
        result.append({'ids':ids,'markers':markers,'qtype':QTYPES['choice'],'label':list(q['crit']).index(row['label'])})
    return result


def forward(agent,items):
    b=collate_items([items],agent.tok.pad_token_id)
    args={k:b[k].to(agent.device) for k in ['input_ids','attention_mask','marker_pos','marker_mask','qtype']}
    with torch.autocast('cuda',dtype=agent.dtype):logits,_=agent.model(**args,detach_encoder=True)
    return logits,b['label'].to(agent.device)


@torch.no_grad()
def evaluate(agent,items,batch_size):
    agent.model.eval();correct=0
    for start in range(0,len(items),batch_size):
        logits,labels=forward(agent,items[start:start+batch_size])
        correct+=(logits.argmax(-1)==labels).sum().item()
    return correct/len(items)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--config',type=Path,default=policy.CONFIG)
    parser.add_argument('--resume',type=Path)
    args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    config=json.loads(args.config.read_text());random.seed(config['seed']);torch.manual_seed(config['seed'])
    (out/'config.json').write_text(json.dumps(config,indent=2)+'\n')
    splits=policy.dataset(config)
    (out/'dataset.json').write_text(json.dumps(splits,indent=2)+'\n')
    agent=policy.base_agent()
    resume_identity=None
    if args.resume:
        from safetensors.torch import load_file
        resume_identity=json.loads((args.resume/'receipt.json').read_text())
        if resume_identity['parent_revision']!=policy.REVISION or resume_identity['adapter_sha256']!=lab.sha256(args.resume/'adapter.safetensors'):
            raise ValueError('invalid resume checkpoint identity')
        weights=load_file(str(args.resume/'adapter.safetensors'))
        if any(k.startswith('encoder.') for k in weights):raise ValueError('resume changes the encoder')
        agent.model.load_state_dict(weights,strict=False)
    for name,parameter in agent.model.named_parameters():parameter.requires_grad_(not name.startswith(('encoder.','act_head.')))
    encoded={split:encode(agent,rows) for split,rows in splits.items()}
    optimizer=torch.optim.AdamW([p for p in agent.model.parameters() if p.requires_grad],lr=config['learning_rate'])
    scaler=torch.amp.GradScaler('cuda')
    baseline=evaluate(agent,encoded['test'],config['batch_size']);best=-1.;history=[];started=time.time()
    for epoch in range(config['epochs']):
        agent.model.train();agent.model.encoder.eval();items=list(encoded['train']);random.shuffle(items)
        total_loss=0.
        for start in range(0,len(items),config['batch_size']):
            optimizer.zero_grad(set_to_none=True)
            logits,labels=forward(agent,items[start:start+config['batch_size']])
            loss=torch.nn.functional.cross_entropy(logits,labels)
            scaler.scale(loss).backward();scaler.unscale_(optimizer)
            torch.nn.utils.clip_grad_norm_([p for p in agent.model.parameters() if p.requires_grad],1.)
            scaler.step(optimizer);scaler.update();total_loss+=loss.item()
        accuracy=evaluate(agent,encoded['validation'],config['batch_size'])
        row={'epoch':epoch,'validation_accuracy':accuracy,'loss':total_loss,'elapsed_seconds':time.time()-started}
        history.append(row);print(json.dumps(row),flush=True)
        if accuracy>best:
            best=accuracy
            weights={k:v.detach().cpu().half().contiguous() for k,v in agent.model.state_dict().items() if not k.startswith('encoder.')}
            save_file(weights,str(out/'adapter.safetensors'))
        if epoch>=4 and best>=config['minimum_validation_accuracy']:break
    from safetensors.torch import load_file
    agent.model.load_state_dict(load_file(str(out/'adapter.safetensors')),strict=False)
    test=evaluate(agent,encoded['test'],config['batch_size'])
    receipt={'schema':'laya_archaeology_head_v1','model':config.get('model_id','laya-archaeology-adapter-v1'),'parent_model':policy.MODEL,
        'parent_revision':policy.REVISION,'adapter_sha256':lab.sha256(out/'adapter.safetensors'),
        'config_sha256':lab.sha256(args.config),'dataset_sha256':lab.sha256(out/'dataset.json'),
        'resume_adapter_sha256':resume_identity['adapter_sha256'] if resume_identity else None,
        'code_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=lab.REPO,text=True).strip(),
        'encoder_frozen':True,'synthetic_labels':True,'baseline_test_accuracy':baseline,
        'validation_accuracy':best,'test_accuracy':test,'history':history,'training_seconds':time.time()-started,
        'shadow_accepted':best>=config['minimum_validation_accuracy'] and test>=config['minimum_test_accuracy'],
        'live_success_proven':False}
    (out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt,indent=2),flush=True)


if __name__=='__main__':main()
