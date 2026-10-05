"""Train the frozen-encoder Laya head for the explicit live guidance schema."""
from tools.client_compatibility import train_archaeology as trainer
from . import guidance_policy


if __name__=='__main__':
    trainer.policy=guidance_policy
    trainer.main()
