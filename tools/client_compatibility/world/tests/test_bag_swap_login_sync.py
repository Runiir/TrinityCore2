"""Exact retained UI172 login bytes and adversarial stationary-settlement cases."""
import base64
from copy import deepcopy
import hashlib
import json
import struct
import zlib

import pytest

from tools.client_compatibility import bag_swap_contract as contract
from tools.client_compatibility import bag_swap_login_sync as sync

# Retained 921-packet failed entry; only the 21 matched login events are carried.
# Compression keeps this exact immutable wire fixture bounded without a live path.
FIXTURE_SHA256 = '4fe10e82b33bcc8b5067eda2aecd115cdf0613b7b7bdb58a41b8e7877803cfcc'
RECORDED = (
    'c-ri}ZIj%%kuLgQ^m&d0?=Su)YuaP&Y9y`H^0{+woan&oJ&J43Y|PC1gu}7_{U$(yMX<;!vZ|V`mH=B*U1X6+WF{UY5{bmWURd*6'
    '_}k~7!^406@>_WE$N%SlD2>@4l=$v{V9Ng>kp51gKQKo4cl-~E5`q8McQ3*}!q30|20#AS3;WOC1N^1Gd*MI-8r<)nfBE^vA78{@'
    'fBE}^``c&u*^B<?aP{xM`0(q`5C3W0{}<BrpUvN)#uu-C{P@Ge`!_Fty8H0(=G_mk-@>im!f(HIuW|xwZY70_zkg1@#}Wu67*qTQ'
    'EhPLY{`<Rsy)e%G@?Ssy{_xqq_#-(~`T6JHem6h6@L>My_x}x-K0EV!@Kptf8KXRj#}$x2Ada;{GF8wwl++FV{g;QI&F`Q85k}4I'
    'F5Ik{i3)<S8WDjB#WM_FOUcJX$*1?<zr4SDc=xA&yL)xNo)n1`8IwZLwS;6|JpA?U!|Ol)^zc95eR%Wz25K-uijB!(NAg*#hHHp9'
    'sVfrWN>$jked5P=f4zHn{r2_!!^>Cqui@`>;lsnLcR#*=b9aBYnldb~kR-EdA`s*9$KQYXNBH%@{ql4C{OjLy_xOMRtM5pwYmfxr'
    'u%CRqs~f#qB@!i^lADVm5p@6Q!`p`ssn@*v%iYWS)%>TDQbB8yO2z;6^WV*X{%7z#NsmVXqjKC)^i8;O|N2KD?B8F%e}A{WqfkZQ'
    'j|nl``EhaGqQX+iZ^8)>$A|krZITI)qPZIP%G3}4o?0D$`St&pUwz#bPu2;e_vfw!!w8Nj$6Ua`-H+r-Ysx7ipbM-Y)R~rqQwCJY'
    'GQ1;95d~P~`hRU`31ym(6<l51{m*dpRNqf@NFl!%EvLG(O`bx_8Q0?;#&3gye}4Jq&BL3QZ`YFoh9mSic7>LY>wHQrhn7%%+SJ&r'
    '<MaGHrQ<+_mg2vG>S#Xy4KxTU`t_d=zx{7RxJb`h!CY{NNfNao)MF{4jW}op#*zs^5{n$XKO*XkAT}|ON9nbO8fa?yufP1C-nRe6'
    '{}W#M;*{!)#r5ItKR(@kyw3yF_Yd#?`W}pzKfhbqH1r2RL&j)_%^Pd};nV9k-@}*)?7VyX!(B0MdxBO|KqaV#)*}iKHV6^KkV42H'
    '9T{6q)1@;SkOCV~KoFuYmNo4rlMBYGCPRbMKcqF%C>0E!3=Ksxp}c^r`B#&2bmhgV3BuU+{`me5dczOzHju8FVq{AD_L^UQ`tY*X'
    'nJtxbf$6w%btI|fDhHG9A}bdOBvqv*zzBn^6P5*qxTD-+YT)MsGxSED{OR>u=)><`zrEkg8319TE3uFm14n#|G5~Ade|Y!j*RNjR'
    'y?yo5mdZ6_V-NxDj$1YH;>uH>z?DKW7-bwkD5Z9UmcNAq7{=Y-&K!PY_~AF!VmI8dT$DeZ#k%~>{OIp+_<QKU>G$NI3jtJRpaFAL'
    'Xb@l;51pJJh}IMj^niBZ;X303EC>~bx`Z6PM;zWm@PP;^4sC=H`|uumXs<L>7TO3${_uV~JPYF+DZdGVx&t2$ZI3?0p)McQK^BL<'
    'og86U0RHsvl=48opa)(ZxPXv%QjX*}@YXqG4*Wc{7p{_nNb%72aQFohWF&Wacn|z_;J-V-veSoWvEh0|!>D0ycvjfMWyi+)d7zE!'
    'gB+1M)EgYp!#6?(irn~}V)VDVbV#@Z5c>DG@BZi8Zglv#r7L10_^2ytEl(0KJBWk*@ZqP2&aByB%;fqB6JsQ}sO_KLzJY1bC9Nll'
    '&D5R;^KsE=MOjVr{Y$XF?mup36_s)f**xqlDuxxE=T<ANY%XP-7>}(Ny=OG0j>~xLe~j|n-~ar}YQ*hlx@i{i?(M^$KHcBHd%J0z'
    '026KueUzbnp_fl4++~0oj1V?Aw<PnU+4Sz=*@KZadf#9gjnpyB^}}_4VZ83I5eaMmn!Chq@xD2(VRY)RQOgf^)w(A}=46=R(A=}+'
    ')U{bD43`du`@xi+ql%wy@5#Fdy;@8C>EDf7v|S!2X{k*4qoUMIuRvS>Iy^i2i=2|tT8*96rj<kM=x6GrRPnLCFtSb_=SK2leK|vE'
    'E3LHBN;7~@8^9?(=Jm@rumA6~nwG8LP3AA>bnGNTa)QKo8KGB``0Cx;dm!!M&Fhc%TWAwRsi{{Y4J7K|CRBEQ%uthgrzEx6rbKst'
    'i%a~|`-fMbK782f5tm%?Yy4n$|MBVd`ycP#-e<S`Rvs$N=UCVoM3|)M&X`eDQZNT=gCTz#Id40&r2kIj__s6;RsyLNhN${8*Uneh'
    '&KGJ|>uN9an_-@lYL}~Pm-Dqt;>g8q*OS_Ds$Ibqq8HlAuw7Hz;S*}XtJ{bd+9(5EQ!ADAXTLhihRFp<YpAOCxw8HeLn;Phz{-@E'
    '*|dJ=Xyi<#`X$CrgN%aI7D-3T6J_-kCQy-S)=#DwvcWKG4&O^n#Pv%RBDG0S84)!Bp2gkDLUR7A+D^Z)B>8qPiTwn?4SZZG3dO#l'
    'IR6VBEut25(9eHAYkF&FBs)cis^($Q>EX?U98bNYDwNvE%wX))%DRHHcHpuoRX&62shMi*WQGRtkgM>h8<xr^kY$~up_^vWNQ(}Z'
    'B`XaSL3hE-1ne2E+e+j3v+H{G+ysls_sN`P{yN6EEK>E1aZm`TSCX!X3{C3A1y>3#6g-(??G*i{cr-<fX<ybohjT24O{-w=&*x=6'
    'L`BzUc}z=g@DHvF_&Y@w16H7fNNH}Y;3dlB0T(HFUcv8FNK2sb59rhI9-V_k;2*pvbwmT#4gB7~?~U)+V&Qid>a*}ZYr3W3wDcR`'
    'nZO6+fUyDeM#DcC;F$-JFu*hT4!VhTfPbJ}7Jld98s>Qsju=232eOYK{Yc@TgnuSSb0pNGzz7NiQjj;rAPC?G1zuBlmQtR7({XCy'
    'AMgzy8AW)a$K&sO=68JII-dOIR6YFkzk$wiJ>z=$%y+c#?j<_UJwHa&kv^LqM$%{M7djq);!wNg)Wl6k`}YedO3=9Va}Ec_p93QI'
    'I8Y)1FrVOqtUXJEmC@rs>6fH@x63$`KDRo(FW9>vj+Xh{;PSy(g5ty!5LGOW=}6&OG@7O{*a65o9*s0Ga&vA}jD(FMqa+2C@CP1s'
    'RpCg6FoD$j4!oeDL%Ac1F5@U-Ui5l})93@TN%X37^cn%o*EA{?qgReez!S?H=gbhSQ%Lv`y=tCbVZizt(JKx1OY{<Ev{Z0MP3YBU'
    '`RhYa0jwg~@z>IxziyGgdY)derpQ|U!cc0gg^tH2^qO<@VrQrUsFz@=Y2&!#M0pCI#0%lUsyn9F%+o6^(PMhO>_*X9dO?pZOssk='
    '8t6sr9K9B~6zzv(NWuX+Ej5@Q!at7bt(Qwi`XKFqZ;38<f?m*DFr!r`k1@UcEWMa9?ZG6bEHdJRk3nd{sJBvr?K{KYF&2;M4a(Rt'
    'y{GuAJtibtdqnS9ePD!m115n}Mu?;h!V*kQ@^?WWtOCnmL@yT0{VfQ9F7G<L9@A^j(JNHs$&w620Zyf8E{|<slpCv^n&q!upjX%Q'
    'p27#sjHQT)DSu(Ya}FPj;tb|Q9Iy|b5HKP!OV|niV!VJ43cA2b{!+;`sGT^%hqL<2g-T!xBVV*sI4-Ow4m(c4(p790e;4#OD#F*|'
    'gV%uyl`Ojnz2Y3bfC}6N3N|J;BGD-X1&X;6+A=>&uUMd0ucy}-pjRK$i_YqU1MGEhIm8qw!MF?zx*XsG1;DYh`n#YHB3ir_9~kpa'
    '1sBHp@c6cio{LZ_ZiC_^DDH&f3|LLpmAf#hzJRy|SKxTh=IuztRMj-HgRz<&F)OLKC{|ozqO_X#GbaLYx5Hr0iFJXqe2MhS{Lo-C'
    '_B%VTiZov$>WVmXpiGK!jAe;3M`UH?7YBNSY6C8fxl+6uY=^2D8S9clY@#J4-n_(`mpJnhV_xFRhuHEyuDrx$m3Z<JOJ3s0OAL95'
    'A20E3C2qXLjF))v5-VQf#7jI|i4QNa;UzA-#Dtf4@DdAN;=oG`c!~cmvEL=`yTp8#c<&PHUE;h;jCYCeF0tJuUa!P-mw4_H%U$BQ'
    'hZycYe!IkO7Z>pmvt8n~`^e}Lr|pIbau=UH#Af$#*(D~s7>p$rdx*pCS9ON?>pu3n#9fz|>k@ChS`{yjvIb?8D^_<-)_iG<v&0-M'
    'k~Klj9V%TIa=5Z7{kYymKtI6WFE_PBBGCenTWO`0FQAM!I*kYVC!=Q}5PqpV_W<)oe=DuD(#oY}o7H~l_8Ex<B4fi{+KB^LPL_g4'
    '%cx^-CU?ib<No*>wa4=t_}$Ua%*64tvI|G4>h=A;<#8y77stOddhnSZe%A+5jiH{ErS8!ZHl9fn!OD9^?qf{)-;J&fyR1jo26zAH'
    '8Wlrbhu^8=Yb4J6jvrqe_Suh^!0GWdQWibN*W}DKaeR&W8NT$q8uOlnnR<I!j;~R3TnDu?*YwP_Fhk!=NSK(BrKP>2e{{$8i?3tF'
    'H1hbG?`f{C>0><zGraPBP}g|Lx-6oO-zUw?wX)bcszci2_et0PZluqqv~3(l=#T4wXYlk|4Abpx$y;^&I~9(3s^T%t+8kf=VTSiT'
    'uf~xorVm3K<rzpJOUKXp<2sBuexI9>ubH96nd4wQKcg>xhNq!i8|i7J$G?kg=9)a_X$}oMmfO)aY-X;xA&&E)f2zMW;uWzozjMd$'
    'qj=^TpSk9b>!2mBh*em8^eiLC*DOEQds_k~$Jf+M5M@uxX!{sqCBD^F<IyoKGd$&J=GqKj_)I&vKdzUDnQQS_9)cb7RLsyU(J`MT'
    'KE9^N%r!c5jUCq^X5=f1PT~q9ju&v_@ih^T>rh2s#><;_=6y3f(CC;JU1T)kv+mnFS{h2>l1IGPGdiy4>ea{eX>-gg-ScmZ5q5^p'
    'D^0|!Hkg2cC`grvgAU9-GTK1!Rb(rv1yTJzwRgIyWBtn0MO!%}2E&G2?(Bc_?&bIOZjMcL6TPsJL&2!POm7wgP?My0ZpvP)M!~B%'
    '1sK#}#N}NnY<tN0Hp>2njt%cto~#^gDY?Zv<?Q87r}#>pQcb6xYdP8^bwfR!)hW47r^ef?noc#Gn$w3tr}Rpk8f~U~be(Ft_~q;A'
    'j6MuHg;(N~47B0Y^DIZ(S8st+Gx|_;s@DRU_Ng;8qZiY6^?|%=LrTwRJ38JbTejOS-7nj1hYh+@Egwzo73t=@L%{H1!*AC26k6ZS'
    'O8dF7>-^@Fb)WX|*}X@0-(&y0>F3mRM5ps<yCn_t)5lg?*<M;6!>4_JD_?ifxR2aU=+2RdaUq*a+Q8^0Blh(BmtslblJ?-aNh7Fp'
    '$tu1UN5_S>_oWg&nRxI}meO4;rM(z>2A;FTPN%`x-h}hp=BM=^v2Ve)UP=jw#m3)nyxz(je@1CcmWthICCsEjnbX%+T4|+~R$6JL'
    'l~!75rIl8`{xXd{x@Ek;C1oMT;EG8$LI}6j-d0+<5-ApufhmC{5kYWC;eSj@vFuwK#mNrQjVJr>5U+MqR5(N|4RI!|d^1H)))WTM'
    '>r4XPA$jaHNigaXIxpVyC+>yidsLjbCztQ>xO`8LfnHqx4fjr@Ge6OfbE4|Sd#93~pLlNA%`?*mbz;R^o$#Ei6JB$5qSvbvd{N<q'
    'Zk<^5(EP+bapK+ytIVKfo*8oD-U&L*2|CRQewq{g!JOz1_Cy=(3BFjl+;8m(eX%F>#hqxoJMmmN!Rx@6?;$iw8h)Jod+{FO%T_Jb'
    'C+^whd(1E2ONrnY`@@O)v>(T7q6&F+IB_p7-?Mo6p4XFmBc5Tt9GphX@;!r>?>W7EFP5F<GxAG`@)w_zC+?k~Gbh|%D*VJfJvta-'
    's-I^0IV?}yI}z1@PrQ@RWm<??zDM~t5=GHUE3LHBN-M3j(n>3>w9-l|t+digE3G_QVd(U>mhnNGOJ(T*&ZROwK=V1@$KmVH0eXB;'
    'Y}@qS%3@#7huSW7j&FkxobO*}3;S!Ol~!75rIl7%X{D7`T4|+~R$6JLl~!75rIl7%X{D7`T4|+~R$6JLl~!75rIl7%X{D7`T4|+~'
    'R$6JLl~!75rIl7%X{D7`T4|+~TNXUY9xy$lczVV$o@C6&lWg$Qvv$ekKAGOPO$M#B(n>4eQhD*+3;+4o;C}!7%g-<V_~Q3p9^BtP'
    'ho66k>pz>n2e|a{$B#cee0u-=%lo^BcYpe~yI1#c@3-*VZ`~74V9l+haPjxg=>aS?W&~qO{(vMWl(YZ-?q4tLFaDqK>pU(I#E@E9'
    '@sIERdiU`0?*8HBtNYjRXZrqO3jvHsI!l0B+xA!Q-rj$B_onB;rn-exqq>jl``P^d`5)m>->X#Lhr9pybocQdK0n^Q{P5~84}W?6'
    '@&4V1pSIL2I1!_owU!Igo}~cl|M1g8N5$*6e}1>AW{pP`^RQdR67x~Tl%d@!rb>=A42l@e)QZ$<j5OsKlZX*7Y19Z<aN6O~i5@2M'
    'n2u~SAy8zTh(akW9VNyaLm50EsblGAuk^-L%3DdF1}c3odD;}Bk=yPY0b7zr8+>}9?XuYAj9nPX^jD@*0hQvIN)`kgQ%PbpDlkMT'
    '=g2xiDR6<!QrRDbRo*&KDXySW0+slfN-v<!Q3f&-n53WrOgWc$NugjnOJ#q|S9$9|CBA}6fssKoykyqlQ64>E6;TGrFwjeYN(10T'
    'h@(={5J*L(=*TK>EmWrO7gGt3YJW^66oyA<gL#F#^#GWW>LhU`qadJ{&NDZmlJ~sy6JGi&sANE;o#Ca1UOD2WH%=#B24{5QC4nwV'
    'K;rO~*_uk$Q)wqu+AFA}KxH_lQm4K=nyE$WtQIr^FJs~*cP>&ftCzH=GEArpS5OHr(Rw{E6*oNbQW)!qb3k?=6DoVM%3B92^%YcN'
    '=sh!iTobrB(o60*PkKoy$w;Iy=82axy$AQbXVS;bHGLeu7_z?iaK~t((wK;;2VNTHCwkdu^DA#1s3ezD36&wOj;W;SS0j&rQ%GtJ'
    'L<RT@B#sePbXMZ&jakBKB5`#El>vA;GeR0{!x+__BpL=AKqBPw*b^;hbdHzljhT0o5z<^SLK+V&bH`Ll63MuaTNS|EqA?~T0C*`e'
    '_B75RQF>$MotyB|T}~y6RFS{|c489ZkRUP>h|@cyA^Az&=kHC%uog)>8RfuAl=T$2%9(;+1fbt(3BRFQk)*ll^u7K$$%OI(rL?z^'
    'X?Qf(7t)(OXBcGF`L#O8%{B7=>`alU5mZ`yI4!hqbk9s^NxoKE)9Y*cerQ$ZLgE&VzVnfl&ytUm9IO}GSCQWfom7rL`=7+}UL(2_'
    'PRl3iIXEtA^!vHr<m*W)fhrI->7+9Jf+($nLfz}f@=!9!-0y&5B`SHuB9B}ZT`LbIg)dLJzNTY&FpvjYl1J#|F|?zXhaa6CIF`rI'
    '%E>2=s8Y(Q96YpKA{xs3pj+hkm(Pp%@2TR5uzCJ-Jmo*LR2%54gexv$#eX;S2LWm+*YZDVAv}!w=ljDV|9!{*p&dQ{)Au9(!~e=z'
    'y2F{eg?p~*4~ue$EJ7dd<lx}FM0fa9J{RRcPRPMQ8-mgEazID8q+(!64n}DsNhJqg<UlMy6kjWcG}2*x4ws}nAqUsVVQ5DgN8$UN'
    '97ONQFQ3Dij=da6|2@j#O|@KH_eA-e$^|Rc^^g8@NiM@Ij?Bo#!cbwC<kGDrjOAisH0$IN#Y8Tq$R!Gt=dbJJBEY&M^c+5&94~Aq'
    'm!Ta!H`Dhyd@3s-!%7I=)<4EM;YAvk`}17O=iF(XtMST!Jlvu@{8S!9dfdsw1I}0Sutgq#0~(99@_<2<A#{~IOfL^Nk%xOCdEiUs'
    ';VBqD%JE}qV33AmQ)vj}yupkB|5+sqHS`T6KpJahVVT5WK%N^rVvSj7EDPPqBAxv_mc{ri=s_0nFZ5?2mru-US%7Jqd9LDuY$lk6'
    '6ig}I0kdEL%g>k3MVZi<zM-fJ#w?8G!A_+?BjrgNhEvMxzM+S{VR>9H59JArBETA!yh@8>NIWrys7@Y3J9HUB44adO>`%BapM%(X'
    'KO^HjKgU@2c^FI7Nn2|w7cdbs@5|?kzJibBBLTaZ2@BZ8k9vzm)-aGy#4%>i=O7<Z<fDL~<iA@dADHEdplCSVU&tx!l09~nb`<P_'
    '?{o4gt(2nU>u?T;tNY<O{+p;+=L_yWk-B0G5!>V-)j<v}RC17m&8t|zYONe3av?cpuaJY-AP0Q89HusvB_03E=T&mx+vEVV+g=VT'
    'GG5^oD{=@yyX19WiC4x#FS|+({43}W>{2;MFq<kl@PkbiG%-8k5_=jsSlssqd;>YqZN89@9MUNHLR8ee!X;AV033(ER?h)Vgzi&X'
    'cablIK387|*s=s{S+-!y9`yq4BTm*+NR#F<@9DsMLxGvA{elLj>-?-OduskodRvxFY*{vM%d+0WET4l-+4lj7k-Wr)wX}Of`Mk&<'
    'f-kj|tYS4Lp#hU9rj+i8N%)B{3H6wSuEr$LC<}kiNWp+nq>m5@OOscah~ij{r7-jf1hWmk#W%>W^9`a-216@!S&KN#pvE%rX@R=K'
    'tNcmN_y$A&p7J@BMdaO+<@1uh0LH)E(ieQdwCf9L^=XVvaaglZTv!sa9K;GARKFg7d0$9vc<%OU3{*M`y?Ry-?#LGyxiV>l0IGyE'
    '<K7U5wF;-x3e#FSz$9JK^J_;Z#)#C0%$w4VGDg_Re08OdR?>B2#F1|ncLq)QJnNgCk%s}Da?vf=OD-ItlS9!cMjXtg4My%D4>R-&'
    'Z@otRAP;tW{=l_X;+nN1)Ax&^9Yr4SeGZ?Ne1Qa=wwGvE;^5Dq+I34O+FjZo9MJB`68}9t^2KWJK-+=;1Z=7?|J`UU)x-F`wm&EW'
    '0E<hj7Wsd|-{gA!5A7)SDw*g1;@XicF$tYVQ0ie{!K^%>vBHMY8j|lkhUN1Tc_gLw6kA|OwGM9?^W$C?6;DQ5<iz9^)WG4j%2DqH'
    'OXEgbhX<jgMS6q#1-9<3Wqm7sFa15Q!@FZ@^ZI)js69jrXrPiEQ;EIdXyl`fE{zU=by4SaMwOT)XQ}L?{>obiD%s^!`h+ch5nJ5R'
    'x~NJ^6G^w7=YFi)e$Z`)1q=skb(^LjS$r1jPw2KU*y1PH;<xEG?w_3cQg`s79_hFb+b~}_t2?=HB6ua2!x&5@$Ez{lz^u<+h50@_'
    'U(EL&Xg{_^I|4`-MT3qk(h!JEQb-<D$|@<iY88&J?Hz_IYI`*dmr23*dOop8(VRt^f|C2I<#VuiWG#)U6tvM$4xS3Iv}|v2*^8y%'
    'E|LO_E=3ANR#F&Z2Beh?leJP{$sK;36x=hGf}NEDJ}m{$N?&lvS2mV{8C#+KYQhRBT)}<&jJa<v>I06%j{8huQE`8W2e5|e4Sm4d'
    'pxjkbFwa;D`VuJ|`T!@CR#F%u0ZahHY4uFN>!86Pj8{lOKVvDV>!e^6scoZS{XbdTImBX>6yS$k<Ex~gp0O0<byA=d*HRc(`3aV2'
    'y%dOpc`?083i26CL2R2LIN(<|Lx9<quJ}K!?!(kh_7UDIW(YRuSmLcNoFRy3JVW5u_5xH}MeGnaNfh?0eb%G6$qRb{f5yE48n$UI'
    '8Ai`8uHMT~t)F>*h|Nn8!fW{-MB34H)jXN?zPV=@SMMp6K`qAO9j%-dua@D(D>v|eSj#Vdx|L&b@8vu1KU!L|Np0xXwkEN7%CJk;'
    '3bw{ZPS*^;HthUI{U_p=ujP1hseFn*a*)rk-d{YFYi*_8zj?WQ$X6^Mym4(oV4C8*9aS8gYWx`1o-qlOuJ$kqY!tQEtSxxFVQm55'
    'Zfzkt1NQr9Z6Wk)3*qv$1)suNES^Ss)1`e7)TUja3@8>t%c{TNK^`mwB3Apu>8Y6FljBIw(SiP9|HC1-)S7tv(SA9#G>%(+u%?9R'
    'YAT<X@IA0?>ktkG2oqC3Fw9qL&S4nGxxw5xM^=vG2JD^9G4^Br2exe;Vks`^OIn8jB-tnzZo9Q-PITpa4a4~EIFP@3eaHgN331K('
    'P@rF-T*x-L2or<xxxWNTD!B~fx>Vj7wzj_@s}*Bc^%wH>t=k2>ZB}l$3Kk`~c<FV8W5amvtiwhg<Z@=+P9SsLtUTc7J1Y-p8~+82'
    'gWWg+-(A%&hVh$Qj15`Me`Yuf*USe4ddB=$+w57GOQc9v;J*fhs`P*G&8o<$)N66c1y0kI%k9~qz8-rv$Zh?BNDxAfT?)=s_G}ou'
    'v^F`vR^t)Ou3@mhsz1o*+aHVra%Zx{NN5Khy_H%=EO3d#1TS+PTEP*F)?i0Xa)!7*XUHT=jJ_sIOq#{8_4!wXAbDRaS6*{6n}5aj'
    '`B&H^{|dXDN)U()9IFLi#_=v(#`7**tfiF|w!|SC18_yN)xJI=sKBRUm0${h)KOfj8pWmd(HKKJiZ6p>HPJ0K_EFG&5A*bU@)f7v'
    'RXzukr`IhOiJSFtoU?`ch*TdjU8DPSW{>p{Pwc1!y6L>!)DZ?@t3!@_gBb&_Y@+B7Q8YrQ{;^VS7;MU`V$5P6zcI9<?5>UT@%3kY'
    'P^#m*(U<K#fnM1;x8v!!VtOL3I9eE1{gPbt@f?C{-N^-HQO9`?5giyF;Bx(HHsRV_vll4#ksU)jdby<U7s(}FCJ#*dIB#-!oOd+a'
    ')-s4Oy4x2=bhOp}hatv8Mq&8s7>}qy(e*WRhiIPfT1M2{_|JqD{k}w=(zlKHe~9iNFe_cnf0#QM9IvsJqJA3wGu1s=J}=?FHOcsZ'
    'Y1cGjS}8T|RW|iaKywEMdC5SE(hP!XmG_|x5!1Gh>n?9CR!I6jj+h?p?x-WC%h-uizm0kKB>Z35Fu!}!9_25>Eao^YFHyDHh23Gb'
    '(a0dOHN9e|SPIFNtFo#sX$bDKNP%Tn?VhyZNMfrHbE{?HT=!)8T+)<5k!E(VVn>x$^D@x-SO&?uWrRCi%fKJ98i)|^S{X>4LUOO!'
    'orL=gQd-qA(CRW7fGMOd8MU16W#P}sq9=c**J8UZ8w(ChcG*~9E>UGSz=IXR6Gd#lY%JJ*z1di>p=yh#m=Z2KPq7dbSMnLGis*?n'
    't1*iP?x6lFJjJ-rB=z-piUGqk3{nf@2#ZS?=H;Z%43>uEoI*EVDU%Y-dj*E|8Ku}{9AOuZBa4>zx$(sI7-laWPoR$|7}Gskz%YB<'
    'M=(&4W<oqTRPF!9gVz$k!-u$59+B`s;#KnKGfEBZDC4?EY*%@NULN5JdB|-ULI|<Gi|Vop*ZpJgS_&}!{A$cH%txWFvBa@_zS&Z-'
    'fH7ms?lTE9A=~XZj%Yj+#Y1eVhuM<y2mYV&8f$KpzKZ{S=BVfBHO3tDf5R$DREpRxw%5waV}^&QQp(|3y;lFNB+AljR#9-DF>389'
    '%3}7%FJKh~EXz&(!EqH$$WdC6R-OSo${a<sL2LU1){bj@Rexa5xIfTsHmpi%_H&dRcc#i(gbz`sn3_n|_6N^clG!yjEdAPSSda_Z'
    ')-Mc3(&#RF(N&qe@F5DtB5KUqegS50wCJjSL7s8Hz}xsw2=-mShyuW8%zt#4M`#*WkJF4|C+$`I$IqDmXxli=n6pN9<FwTk|M4Mv'
    'g49;6#U*Y?wCt*J8f_S-A2TzE>&Iz#`8Z8B_6G-(?JoK%XH6K5)8vrJ%Nxnb>Ty~ahOe?)$usT`WMhAzA*jwyvI<q1vdPdN2;-9T'
    ')$?eeU0>B7$j1I~E4%eEGUec~tv}%4WIvBfKI1Vy4Ov8t6iV{7{Xr^euFD*S!!zy=kt$6WSJ=ss-5M3iD_A68>Bsyh;jms5WWS=g'
    '#?ObCSN<Bm66sIj8QM|SD(Gb^>`Gm>R)J-|!Y(ggVRz}!E3@G&IjnMCK`vAvaqcuM*H=^CIz(fcD^3<mOlI@vOpRm4ICH}0*dLi~'
    'X+k+n*=J8_D`$31qOtT9(O5PBm2y2Vapd`o!<2btfy(~OuJYD_N_hp9>C7%{!j#H@tR3&$D!ZVf5F}BVv=6Y85<<NZ!<urUvYgq~'
    'zx8llqzPjxNj&oN73%arU5XCmGbe+37!OCNZ)G|TFlBIp_n4F;EJqAN$MkZ-!xA0HCp_d=@X!L4aXpndvMg!KT*`SzZOSB7pLEwp'
    '2bQ-ERL0Axq;cC=Cn=ZRT*$#3W{kBo9QMO&iQ)lkPmgufaBr^i8PoWD$2uCe`Di@!mX7~8c~!>zA8ZYnE=jz4tRtR=$glCy(D3#7'
    'XsF+oVOmj)yR5p7ipobo-66Yi;B>WIL{P$zYqIK6|LikNQ)+11SFm6UcF|##uOI}XW3mOg3+Zf{gB%XgeO^Z#R-fo3((#VeZ?gr*'
    '{G$Cj{Ll_P=>M!OXnIMMPfX^cU=OyST4xLPHY8TZ5}D05Jz96C=_Dtyko{gBp_Gm}vK{zdorpq*b@w2_ZdiTtfF#OLbB#St%SldR'
    'lKoy>w(h<*v+-00z_I-M@_C6p4n1NMHrbTXxX<{_L?w@5-JN($=;}V98BAm3RoJAS{|PlTonSAQGJeY=YyzI;QwZ`I%(Wbb^>!Hi'
    '1jAcT|GT1J^y}?IJ9;^!?{ji^w2a@VpQobB=c#n#$xV);E^7x&UnXO=9A_0`t4}1rK5g|mXG@*z7vlM!7{oUE&jKg7vuTMIaV!UR'
    'uxW)Ae)YO9O>?EI)>qgw_Mb7ojsH=C`m>Jz5?A~mY*!{Dv1~2>gHGG>uHwIc#{75N{P~Jg*ZGeDh${ajJM7$YVnZBC+Htoc?%~9o'
    'j=8TV4u#om@^B!9ZoNGZu48!|a_~k1lZ(~sjR9k2uabxTLgW#9dBiK^VK(BErv3O3Ft5i4d&u@6a13kl$!e(ns#D#WdB*spxA~j|'
    'roGPzna<BU@LwIWXTjtUt=@YexH)epo$@&`{q^~rnA$jQ7!=aFSISO<t9dpX=5-QFAHwQ!gL%xa$^yaES2S*Hjpt1#iL=f(8{OFV'
    '#N;81lR@6DUI&iR>g(*NXB^MV*v9@qEbaP3NWUNV2Yxu&%-FbkzlT!V+i+EXU|&d_(3No!FTQ)>KmQus@1KA9`Nbb!#9x2;`@_%X'
    '_s{<baOY?9_W&0^{`m2ShfnXne|dlR@a|9lcK7NY?)?^i`>lJ%39Px56fXY$IX!@-PI)F^bom34ToL`>-~H=_{l)(ievHsujqY!s'
    '!_U7TYJ8Py{BZXlpYA^1KfHhQ@~6A+AMRiOc(=Y@B`_DGdMD>r0V2|T_8HclELQX3<);rX3o~B6d9#`#oCZ~)Dw3*nmrp_xSYS0p'
    ';{?K>aRd((;aw==Fml%vjT1|!lp<oFi0(uYOrt9e&N);29;A5;C2-J4t1<LSk-!Gv3Sg%1)qNiiA){9mY2g-T<;I)-JcO9g2g5}0'
    '*n6Cvabv8NX@yr)juAQT?`4hnR%LFjxhfdg!_K~@<Bq~Wqu}%0p_KEoe?6V$UARMHG%BPOAi-91M?6FBNSw3u%yWk+msjPxe5fPc'
    '2~1L&R<j&KaV2-~v*V6{X&@46o;TWr9ARM)Oea$`v7{lLM_bM>Wz0HE*73%mXQ(+mYmS`fj*2wzfl@LGBGXBA%q8x4l@1*0CP&z>'
    ')Exf|xx+Fhi+Sz@m|x^*F@Ssm{R+Oaw8B~9w5IV}C%I#vA$MrT<YnE-S<krx>q#6?C)$+dpGKWVG_{gD;Tdv=<es&lJ22<SkvhV_'
    '#LpdK_%6~N{S3K-Gk4U|cuw+ot}y0FcM2+V$9cjXO<)*Wi8}^AL++s5vlh6+9ixdm#zdSB_A5C9FF|EPp5J&5&0g$RCb%4Doc7|-'
    'QNMz#QfnG%A2qtFU#aJ(IVR*0OD$nC>he5A%kvrHz2=l`l+!GgCpCvYL(PHt>C$)=)5I)ARb%W^qQx?rTNSjHG^UvG)#H_Wewu?K'
    'O&ba<mMDj#s1m3)y@Tf4P&{TPFSR?7a)_l9u+nMu$ihF*876FP%g}KI%McIK-!C4ya=-ZMiidB`pN0D0C%^3YIy?9bbA3*A_bux_'
    'QNrBB4%U6z!)Ny%*?o`w^QLDN9ntB$gF;8~fJBXW$&==gz{8v`E_y7-*QVc%ARaw^!F>jfZ?te;f3EJw^x`UM-yhYfA04e!)vt(C'
    'kMCHUDi83)3w)}mnfIRh{Gtk8ZqKtQ3DGGEIe8<S;CX$0p%gTScIQlg`K4enC>ioT86|};SiBC+r|Tu(0-Ae_<}(N3)A}}-aj2pB'
    'lcB&y4&du?;vzJk=C3NBV{N(=#TuGFF`5gMcONBatkAr^eg@4I7uhGLMWE^2L1w8=Q9Mx#;p1A4e5<xON5|8boEd&%Q%%1U-S5gI'
    'Ppn0FoYnN3D`fJywz#Wo^NZ1Zx*MWs+n`Mi&7UutO8`QEa7Kwa^0w4>&LFxrk|abYHb~4<mb}1nT&7AVFE?+?X+%fC%$~C;M15`g'
    '9V^vk2BlA|N#8c2^U3Fzg6Pxzo@WrfXwx@~=;W(FbW4>(Ow1s9edi3KN6{gA6eve}S?Y2I&a$twd0b8*I=1tOKEy7UCnw)+{339)'
    'd0Z~?xIC4OE})bXV#Nqy$J$gO*#>)|+2~L1aWPaed4%Wn^)qPhrSN&hT_TNB6qNLN-<rpHV}C>Q(`fD*nm086V$pm<yBeB5F`849'
    'P6<l;xTdS2<LhV89B?$}){RI2o~Nu{E}x5QnZ!A{UGuh_Ky%0E^(e4f!=~R^$shCd-WK%jqIrpx!))V&PvmVmI_J07Ha2rY<u~PR'
    'L0^TpMI|peHAEkITk1P!5S>!q+2@w0%z!EPDNl%APD0#(=#w)OzXe1epXxZKy`1JaaC`E7E+axi^u5ca?(=ds=Os9EjeWj^=wogA'
    'Mps1fSKw`tfZLqdBX7(2`WZCGG3H&;3REKPbQKom?23kR5fly0K0oPg8RZkKXrE|T$tzgOkRPz2`BOGO)Sr)UpQ}~B+KT35ZK_aA'
    'ZK14rTb>xr#R8g(Eokm?1}m*tz{*jnIy9Hag_N?Oq4{H=`H%(q>CqfFG=DB=z7*Rs)~1H$&lb)30-E#nXs#m5d-_ArF6HRqp+j?J'
    'EE2Y%d9%$Mnm60Lq4^GI&KA&|tw(c-MVCoJ22IQX&6}s?QEhYF(7d7ft<Zd|O%2VTDVnFVWaoGJ)AhUjRn%QJGUWk%v#R)nZO%k6'
    '*0-Q}r(<oGf7|8%jC#=`8k~Hr?ecGEerq%*h){JDqd2~L2FXL(^qKQYQUGp8wU0QTgKlh)yhSLUiBM$oI>aVB`lsJ5?QOfK-{Joa'
    '+vP*N;MO?NFDycF(58mu&)Lg@7rZQZy_dx*=1N|BN?Sb3PF@z&ye!Sjax*UrYF?ISj^@OG{T)Ju<l}4Syek~5gyI4jPI)?sN}AAT'
    '-Qq3l))^GH3eBF1?lG!%eNMke-fZ$Oz$7R2=a*uWhhD3~RJ#^Xe9)$5lRsmdJVq+#Z1U>*88ioE%_j^fE-VR-`haP&$;*jB4b30L'
    'CT~%R%_iS$leehEuNci~3{*NK$#mtjx_$=DqmU-q=1!+`DiX3Pll<i#Sw-7v73circ7EsC+5CwZ<?{tv{=_FOUrYYPUYnY2{*2LF'
    'nwU`AQc#h}j{eD=bM`slH*!vR>orQ=7Kfq%d{kU(CDtN3`$l6~#%I8fX+M{7Ywk?<=52X0B-qG-8@R|Wie;f)iBm)$Yg0q?=Zfeq'
    '<}I7-7||zp&LBF`FyD0PL^-b*02tBUfwfK)iIL+i{_}4U(LI?*^s}c{c-3;WJbk(J)C&1Dhz{LJ*f4Wy#YmePqCZ<3J(<=3iB8O('
    'OH52YD=u(omU7g4!IEb@DxQLxA|RVbE6*kN6x->#Up_(g5v|NDk8srP^{2~fjDWyd-r%V7$xAtCM~-;oQbs)n4K^HwmAqlkjyKZ7'
    'c*ACAcauA3Yys!FPqu)=!eHhoQxv812q|Ym;^wbAGrRMb*#a$J+jF)B@WP4b8%%(fudUevQ$!C-{<_JXGl<TK;2F`W<oN_EXLUk!'
    'gAKOLU)TI~&0p92bq&!UAJK*PR4RNN9aUXlIJD%DvyHNZ=J~vnwE7Z=&1lXQwS4P&C*d1IbF>g0r6yOW-<`cYC-05XoV5LCoA;kx'
    '>8m?88Z4o?HX6$DPU5jPH8g*=Xzmu!+-*Vglx))pX(huXffw-!%~?v!+0eY9c|-Gt<_*pFKy$l*=5{@rJ4#iFj7s^GJ?m`qt@_!}'
    'yrFqR^M>XP%`ZlCvw-GiJ(@FxMM86Hn9jDjBQe|N-Uj8GZQjtlp?O2|hUPn<xn4kXy&laup){en2|=a|oW(ZxI%q7n#<(^#Z)o1o'
    'yrFqR^9#^iEugttkLFg99Mh7bJk!D81<m14u5m;2hUN{;8=5yX-vQ0#0-DS9Xih24Xil(1V>BmDkw_bwH#Bc(-q5_E`J<z`^kOmQ'
    'Tx^Lsmze2<=*Un>yrT{gmk`|s9hF$il@@be)81mvpGi+zM1*S)c@=<Ofaope{HwOl`GS4Ux7g<>$F)R36!r)E91M0&Xj=(w_Ib0<'
    'n|<EU{L#@IkT>t;KRS!Bx_-ts_cG)&PoU`%r|rWU%Y^1ZIIG20G;e1SwzCMoe%rjAMcB~%5o~ixB{f7J+2-TxXVCmyPN4N@{w?Nf'
    '2{Q)@tjVwJ)fbbmrR7(C_W6~^+Ek&~hITbHe{wV@3usQ(qxrckW)007nm06WXx`BLk<nawyp&sca_0=9D~?U_onsPcI-8IP41)oK'
    '52L7Uxs@L&w{lPo(VxCNv)szj87=WlZspK&D}M!uj#2~*6EF@>5xu^12GNDkGTG>ug+PR()M8}FCA<97vOBil*!hGO^Eq8Q7uzDt'
    'r8!n_j_A#QzCE_(`g6!GLiDs6YV~n!%UGKlqCZze4{Ryt`Q*+SL^sUmGYYxE+&Gt#%R3Vp2>^1&H6QwAInUX|ieoM3`IlHOjBjZ<'
    '&l{pY0;1DJM5kL2ofDn&Dmo4?U@88b+jK^u<=6<({OAqQ8=^NvZ-~AFqLW2LC!1{aKuOM&tGqMJ5n*C59v-w>0Sq=9y`4++^_F%n'
    'QA6}E2hs7;9?{92Gl=e`*U9VRtiwjSbb>`l+mVbwrtJ}JdqltL()NfpME`OS9W5d{+JfkypDx+x++u79*ysf8_6Ug13}>O8G}jQl'
    'A$mjfhUhyWx>|}}oZLBs=-R}P<Iy9hQahq(h!*hC1x^#*uJ^ipi-_K$7r#ZXON(A?i2ewOE*EWdxy42g&gJMu8>#2g5dt>86^wXz'
    'p1EeDHygd#=*>oNi2nG9ZX5=xMS?_@LJk$dBT(c-;Org8#Bjh&Lpia4iqtw{0jDL3fVXom=i{p~p_V56C~HaL7q{r9IZ22BosBkl'
    'rLdga+k}x^5qy(((;ADB(DS?zg0LK~sl4U{#uLMQ;*FC;Q@CZY4JfYTjbYD@Hxd8<##yS7nA!r9J7;VGX=R?>!OTuG?Wkbf8_Wn1'
    'RAAhqq|WR%=2*?4&~)xL{q7^CUjPQFdQ2)AjAk+!eVs+E8JTCwWA8TJx~4wTrf<m>81(e3$m<qen!^P;&FfZOKZoX+=k;_dg-#X&'
    'wmPKT5hO+bG&Dbh=77?4PLIyzj)01NXREiF-4m8)mOEkz&5Jg*nccHSbDOO2Adk>|eEkfX1CHiBX&3;OOR&wk)(Oo$Oy;y{@vf)Q'
    'T>Hz=9Fwm9;fCf7&96rDqD>9WpEa7B`JBtu^)qNrbhOAgA)_$KV?~V73EQGZ(dm{2sO4P#ic8D6+|c~XL36!;=6XGvE3Q$p%?)8Z'
    'p*a&)By2Ox7#v$v)Z?HzQ(pvzHZ=b#(0r^-4b7h^noDca8oFnW&#e<XPx478l)`)-a9UHX()y-Npanm~3h>|0PC$>=iFrDlmLBs<'
    '(i_D4ozk!AoEBrca-EoBPoaS%PRF|H`kArLOC-9}VvG#J0e@pmr^R3^m?Ujg;q+K%!@N|_`JtTa<o?7%Uh_kJnSQ8^Ys5vH+F19D'
    '$2x)?Rb(3RGroET$+^QB$+Z$8;DqEDr4<FKspai#fpaSg>Ov&<1<4V4QVnWI{v{&$#ubI4O%2JP^Q;BiWPi_`6*Ika2GNP8JjcN%'
    'lwpqIz+{@=C=d80Hz7Lv_A*fiGk;nPOn55RPrtXENY5G2FF#Yc<wSZ!J$~+pZm62iayPki2GNC}dDlnuL>l1;C0wQ~cQkMZ-&)j9'
    '%X0VimX_tN+2~&iqEoDsC613G@~i7-(A>+;K9`(Rn79od7v^nHu6bNeqdB|OcW#^Sym?%1h2}+@8k#?A`&=a}oTM0&seNAGIfLlI'
    'LE{0@Q7}G4u*fm!O*)^K@IYci^fRlW9$j=kuL}*)8=~I~(L+P@ufRT+*{^aG$5~xJgXUJ@Y@Z8)kr$2-VttBjG0aDyS{!GK%KwT>'
    'i^^|k{^i)`f~xuKc9T125FHt4xN*V@3l|(w(h6hKu32uBZrSZxcDsh?$M(z9AbQJg_f;c0Pk!>b4Ahf5XAoUl*=4oiIw<W(REk)z'
    '(XAv3KAVkxQ3mRBh~6?#KW9X58K@hgKLVn&MH`)MvC&nesLNAEv_XzIuA&KyVC}fZ%|>rFdPDSPqc=p~0nzDV)FRyywaA@e$?Fm@'
    'H4!XM<%BVSpPsRljkrZEwy4Fgx3s9mhUi}oqLW1%oouqvx#KxsnT2PKBL*XBG(0GIw5ZwW%|>rFdb80RqVIs{coEU@7DSIin~dmO'
    ')8JFA3--xIXB0bW8=^NvZ;0Lyy&?Jzh>jLlM$xvFQL7W8J1n(Tjxgq|k&JLdqGfGm^pVcyb*gz?o~_sAsa8gzI|&<RRz_W08GZhU'
    'P8Mx+vdKp0M0D}!-bfDk<Zw_H9>l^h+@cqojoxhZW}`Pm-viMXZFI89Mz;#(lWGa$l5<CB2r9+8M9>l4Z1l&9Ui8gIf4+$R#o6e-'
    '+2~(^*Cj0a(Zi-4Mk!aPal%NUBp^BtPNp43Qc0skv(cN4-VnXn=nc^y9nmR?3Ae*h27v1N88i=A`h?~Yh2(LeDk_pP=)%KZ`IgV+'
    'Oipxq;VG-KowE7`l&|HKRoPBieg5{jL+K<ZAvBvi$thsKcfe^bR3H&B6FyR=77r?+3_PNpn9nM5e3Fwk{3vrt;up8KJ)waB>d|O}'
    'R|-ozBM*$^%9EUgjTi|&&zmS@j@2ZTTgnc+;mir^U?d`uV7HPt?Ah@~+JFHMmbil>mt7<)40`NJ&5_TLJ08PmZkVz2x+6&9PQq5O'
    'nkXUE8^MUcMp39aAZzExhZ*i*6Xv)>;^UosGK+H<>DAnEi91WW<I>y#xT9d)q81pGv(Tiy=g87@ew?=o#g*LQ&ro-4?pboFXR+L~'
    'ECc%!cxAD{mR!i4`24s-<B~^da_7t(#8I3*O2}x5U~H3=%M_VO4fjShk5cm}HIGvBD787r<Ih28SlSOexpM~5am3joXU<AY9Q9xq'
    'B}6BlhREA~*tQ?`D=uw6Y(w-f1<?gfCtY)5CwN|8KWm?hymLyRz-d||pcto|?;<E++6mZa&>S-pX7y;IUsBZl(xTN<pN8g-*Zfd_'
    't}YkPt<<VtZAJ63HdQF5woum4{7KQA!vB@aXPwq7zSZ?JXwF@TNIN0DjyO2VLLfRa;sxc=P~Xt}6q=_L+;e(lCRrM%-?8d@8hK(Z'
    '`nJ)W)Sr)!=0#i7ZC8BN*y#TTZFBThpm{z?kK!XVA74L%=76IiXC9N(QUEUib)VKCBvFQ%W}Bb!w1{~<Iv2mAbQihP;&-03d?oQa'
    'MVp$Z<ym`L)Pko)t@pG5GKw6@;xVCMn_G%Z^0a7xJ1QHRKa!_~d@-ID+&nGM#nTd5^qkFjT1fM>d<C|-Odb_}>}eTaKkI4X8O;&n'
    'f?-Di!)^AP6U+&1Xnq>ar99T8Rk8Kxi;1nr%{G57w)qm87j0^``Lnjo#e!`v*4ySnbgQ6IzyQx3bpU7y&9Rq6(-zb6IJUWoZ56cH'
    '=38y^B~Qy(o0@I@OwnAj#Y_flQziqVMc&=OgcTk+5;(y*?i^W*TSnj(cm7pF`Z6M%wqLF;E$+M_`V`UqBBJ|kh%RwPbQy_djzkGY'
    'JK$c>#5&dxy&-x-^oHmS(RV;}x0F9}a_0=9M<H^48tOzo{aSJAQnoQ7s91kiYRezF4bj`_*UuTz+v(R0(H{ZP?INPvEr_0%J^|5v'
    'BuG0)a<+HP2oD%5+YtSc5Ir_TZ-{;~M2`*8zXC)zi(VJA#p@C<&wg}g1&+aysA=}2TOA#d&Fj*<E)CI}*QFu)4v4Oo^0!RxoI!MC'
    'x~zDZ2%56M2~2bT7A3f8u`Vrt%U4}m{+5R5Uk;+HMX!t6;&m|r=Y66QOCP{SR|bWY=bbQ*xo%#U=0|Tf`WNqYX@2yt0nx>x*F|jc'
    'y5JaH%H!g=LEZwQ19qlZ7a60~E!L%ZT^gb{uS-MpJrJEO+URVHjUM1_Iom!rHll>+mL?lrDeY}&Hu_~Y`Z=#lJ1g}$dtKUDsSVL@'
    'Szdhi!hilXxZgkj^7D&7zWDu@2luzn;pgAs`p@R?0WN*~@#7B<pWc7}^8W7O-JkyL?$tfq`z`$TTla($SaT~WT>SlWdH_oe7>+R|'
    'f53=oPU(Mt_pcZB7ynQAb);SbATbjtN_&k_U^xv8))@h(<iuZp`TN7q=J(J42or){e){mTQ1$Z7n++rZL8PWgJvl{+vYI6Q)Fi<e'
    'C2Eq)lanOHge3daBymC}y5ydmB<No?N&cxx5@0G-Bn9Yk$$aTZvRasdB(f7pHIE|nH;++IkVFIz1mS%MlDO9GXr7!Rfh&q&Qm3Al'
    'B83UBNeWL+lBh>Fn9-=G)ohJa-Ptf-BxxrmX)#f5ET33zA}Mo45~&177`1zogpsa0TuO4C(l2);MXYrp3GbszA~B^RDb4SnRJ{d}'
    'TGu40rxqNY7;h;&{D~==Xj0mO^t2QuKmCZLh1th))%UM|ynFcg)7w`MAMXBROT_{)alYcEX-`${r@N2$o2nLc+GeZ}i3Ih&t+}H_'
    'Se~78B#F?%3oJq5S99sjyO-ZTy!!O#hxZ@e{rUBqyN_GQm7o`6a?8XvFdceg*`n*<B*9DEy^dVXRZT9*{}5w+W-OdteMeqLglBv%'
    '<jlNyndcwh-@SSB@WZ<;v;(ZmDeVa0J;&3OZi%oJ-G)EfUs0;d@m4<f=(tL$vCY-xVTXU%NQ9Y({sqRpb%pqY*KxD}Kj-Ab{W}N%'
    'lLz&Ica-LiTwM$A=rZ6<*#YnCyuE6r{*BnOg(aGcF-uC$pEO+e{?>lT?o}&x*EOxLN85R3wVzyf-E|e~>nTfm_P(VPO-I+^TfS~p'
    '{d-h?&xhZ4_gr@!1*5Cqd)i|U0KvFk*<DZh39H|e{{5_`Cx(uGXY1du*47NP4?n#A>)nTkkM}R{KYe`o@zb08*YDqK5fjkB@r;<x'
    '9v=cXNj}asu%-J+bPNT#cppRv&(o#*CllTi1B?w}=~<KmTMy5&`o2VYyD_80EWAM^K|@c|i`1P;`AH2)f?uFLwLPS^OEPzVWxu?Y'
    '0szjQMcGR*bPEx<nnicw>Y<Nb1E0G<og_r_qd|6QSd#qmVQCXls&cwzo|fT+T|b<ZX6(gd%5d$~FcErCEY><Q1|#Q$w_YReXmBVR'
    '#Rv(SADWT=;24>)F(Y(Z;dFwfL%DrA_=wtc)ca;Ye)sm_$9Hc(-a~i%@!emyHBL|5|1OSQf7MikJih7x$0|qwyv*D_1R<^F_F(xI'
    'u2&_-g3WlV9G2AU3Mp_}&zXG~YZxbjC;DK};uzYjoYm>jd+Mic76I8Fp1QVsMbnc(L(js=t_V4OKeS$Uwt-V=DQpi-<9y<ZyS?9g'
    '3pqlniK1nu4~n*)=>tj?<}WB3xl|mFpl}ka$6goNL=LC?kynnkkfWw9+S{+KZ6b#Y^~kG_TgcI9x`3sglpH=;yt@4Y_9k+)n5eQC'
    'W4XjkCkQ~GQ3N`jL&RlRIU2v1t}(`G7@yK8<vC7I5)*aW0=ENp!*qpAM9!a($1pjPlZ9q>>&3V&<PapLMoSj@FqW(r`ru`p-MMub'
    'OIEAH?Z*y<mC`4;?<Lq|)`^&uJ?#V2SmwsYBYQXwj=)^32qHacVP1$Out{T@p4>yj37-a?;3u?$73Fn*3wR77UV`y!Q+@*nb1Fv+'
    'S0Sa0XZVQ4zMnkx#;h|zb}YuxU`Mc_E}hPYSU@`&f?%xUiRqO!h#{N(IqUW35N(O*>CUoJvmT+dFjO18z~=GX5r80dVs0@uplkwW'
    '?<RsE$+WE`)^kVYa55K#^hz3?0!^h&PwqH(R7`U6$YCQ}$l-J{Pp`?*CWfQ~D#F;668F&%Ehr=7Q(jYBE7{SL!Lan?9z5oicRvj+'
    '848A>Wjz!Oy`@0H;(T}`NIXKX;X+PCDaYL=IM)%F3=wEFksu$Kuro1jG!A`-!Nn~HT?L+GK|2nj6v+)P_7NpiLmxSWXbU+|ADgNc'
    's$4Cr!RfG)a?aJV5w;#dwd6Fqw3Y(V(dKQ*Q5a5=S!Hx`)H8X65~BZJR7=Es9E%3Na_T7XEpHvzL$##f_>tq~wveN+&{Nd{EIw>J'
    'S&zkozulfQh*zTYBdC<(lAPea;=pzw46JjWR4SeBkX1@e8*6B75QF`b(JGP{SWKsHn%z`N>FJy%WAK0u>oIuvJIw8+7>jTvIzNI4'
    'HKUIlxVVX$$@I3S1~e)gvzcQ6Gzuh>j9F%<oY%fEw(mqvX49Hdu9N?fTD{i<3s7;QPZ@ZN(Z3#c2S5;W>u!}ctpnuSYm-KtutyHf'
    '-9%0mZI)TD53FAgPo)enwaEIF!1V~M$BfAntXF9g2|6L*8tyjm`P^7HZ7f`_EXNeHm!7nd6KoyzE-D@O={s0WCR(?T&)q@}q4oN1'
    '3VH}Rn^zx@u@;|(Kp2nMX@y#eT#ukoL@<4V_f}z^2ooRzFJKrX*5}3^EfWPg0b_-8AAz0{^I=cQ?gqxBj?IHcrA!Z_C2e4R%7~mC'
    'CLT;F36Nl+QAhqtSx!{z0Rg6q8FPvATEY8*lqxOHmXRO&V^sUNCp2Z6KXRb`7IGM_V+vERp@&|x9+`%4FmukHT8UYY&}*pH>ICnl'
    'mDy_ny*VGE5LMb*4vjtX@!`oT$n;4U1+_c%8Yao4QEc366exElO%kwOfHbb635;+wZIse=ui+vc@di&S98}7M<)knklmcVb=iiY#'
    'd1o~za?(grHIlomrqY4}gSl=nk~vxWk-sVU-Wkw0Qc;r=et|@dPL1T6jH4{T@{4w_M%Mc|Q(sK5Ui#vCP%mWw_vI069o#=cU*v*M'
    'a1f6r8ime~ExD$_r^aHR7Lxdpo5zP*qDZTp9)blDW9o~H`IH`FXg=q1CttJ{6R*zg_jzriMxlv?BypWfY4r#@N-N+_N0(eU_CA8f'
    'Nz6_NLt3kIc5ZmcDn}S|)<{q|dIbJ*3jXzz)SHl=+(W@6pRDVXsu$&OA)AkmkT8oP4v;+g;rWqA3uI8mXkpTs%Z3onD5wIw%=SS+'
    '-I|?OHpaL|BNdqjMWu23;I~^pZV!K-UC3TJqCbL~0wU8#-eb6l9623%LuHhwBjQ2%jTB09M{sa5K?Xl^kx1HWPU-l@<!)n<U<$+g'
    'tY&G<jvnU}JbP#sOgU<w7LDV^If`@Rz%-C~g9YU>4?;&Ht|PUNlwgu=Tn&~MCh#Poai_2tuyLnmgv=)40Q2ij!XY(@J_qv`8jFw6'
    'f3%oDBC8a3=`>?;WLN;VDqjoJG8-1jfbcYdsnN->czl`SoaU)+l&>2#f1szJGtn*8iaoJByEwJAI4ylS9@xIo-f8TW`jI!DZXpN5'
    'm_O}5r0PGbXB&ed?oTg4l1t|yH}5|w1Q<>Fj~T1l(kUi_%>aHC<s*d1O$6)#1$BTu+-Adkw<sT+HhhRj-Uq&g9H>@KRSl0-ZT&Q8'
    '@V|s}s&?T7=@C?oOy_{Ca`-K!ZWTw?tJbykDxfo^Cj(5A(?9IN+@NVRiaC@$awhjeH;VW)SSHOp#^&qVnaA+AJa4|Pnv*<&OevqF'
    'Te^MnhfU-tH3f50^|19*q=C=s+>VM1Cr^(c4F&)=RlZQCPhM-k4^w_RmrQURPP5Une}rapOit+FQUXzN)Mn0V227s}gsHtuKrlZi'
    'lFXBpL6YkyD?@Tda&E<R<uv9oBzUwDidA~M-i$va7e2QzvC_bQgw_gP1&N}u>Y<7H(mH2kj))_NJmse{wN3`uvu|3?;yp2(&eIf5'
    '&}42#lifs9JVBGYS?m0*T9-E157`vXz6s}KtRtI&j^3owR{nmU%<`K^*L^He3rUrIPDuch{#6tyjp-sq<D^yR+omSjXvyeJepB1f'
    'QrjkuuB#+hd795_lUvrNYLVnRn#j%G1p1WD@>=<(#nZby#VJWeSoa=hYnPN7z#b?vx1k8$1c;J$!``56fGBC=wW@7?+P0$M@E*`_'
    'yOu|8nMXO{hFy&&co|J%r1BPM5<w$}Y&2&nihSad9AN;EcM}ZoG$k!@E2VGg35v$?Ugx<@Fj>+_FzL6n4KL$cN+7)cO(vdrleo=z'
    '0&h~c>TfCGjpOUy!=_W3k#-}%672e%N9T1QF6E|&HvyJldy_YHoAmYC(NdA6zMGQz44IqGk4&22MGX%(({Py9fIYtw<BTAF=}lF{'
    '`*|%;%N(z^V_em`lmu$X-L>LPCvX?$V?(yDvu{dCL{L2)I=snK88}`!I{Ap{QtPT6QCC?N)i$~7EbyDzan&}->)wQK_9g;vx{0k5'
    '=*`~5ZuO>g9`9}5M8&N}JLtR;TfA~?5oYPU)5&h`t90Ch76i3=+*Heaf;ru--o$Q&nN?ngH8TUd_$G0yen-QtG_%SKa#ic9=!L6V'
    'S0zumj^p}fZ!$M~lfBuS+|AzPZ}z5eD;@XoRydwgV-A^2&trjHwtA{ea98<4@y&dp)#i(<kPd7xWj$JnzAh}!?+Ln<&zRiI=TxOA'
    'ypH4SX0qeA^7JBk8w(?+%REa7U6`w^UW&T#Y^Ibao=uljvy*$YHnTPwsT6*8i~hzqrAJt!N$bYbW}9)d*GI;TmQv3oz1SEt^BBz*'
    'M+q6~19;a*X$%|d^tlD}3*$E)q4|m&MQ_xnRjyx59+aJ(i{4nd%={S5t%E1W<SJy;FqJuCLxo0^OxmsRXn;A^pfk^o;5$95Hq{%d'
    'dd(H}+D-Mws$O>m&HiGVtDM~Do*XS0QX|q5q2k1@d2-~?on$FL_vC0vaFSpBEVYLvz(lRzKrI?kJBfzbrV(`**IB8$u~h3Yzm4^h'
    'E1vB(cdmW*VA7|}Xj!tDu6c5_JeO)U7uPCr?swD>z4=*^7Tt(gMXw)c`cI2&>CBZ?PrC7w<2?3fbr_F(Tv|rEpvR5!{-1klv}Bg@'
    '`Qr=w%qWxp+2`n(H{*@PXL)m&Bqdte23qlmR*@FD);>8h$<veKLIjjZU97RyISuEY94%WVdQ%^h-T4h?={+niC3<bb6DBTtwmLWB'
    'JZh`4R7WRDoJG&W($gfd!zN9VX>kdL4vXa~jW{eWP4bhRm5my4sY)udiQekWkn>NXF}0)9M9w`qS{wo%rR5-&&S_YMoTKHSqjXH$'
    '#-=(O*G4PpigCP7Ft_npe8saQYsE#QVp^=Z_*r)OvrJz+k_##>#A4~QgqTQ2bew;7wB(YW#TRRpNXsg#aa@htnwC*6da}woyKR(A'
    '%OubOyV5?hBOZy%wU~y>H6ks2Tt;yn`@D%_krp>Ds#T=Lj0>MM7e8q)e$rk1q`z2`!sVKjmK!den~cxiI@@dHc(h9k3YYpZ@a2At'
    'Dz(Qp8zwChurxbaWhIUl3DV{lbh+1tTrp>@&&%03XJuE+clpJh7m*zL7mQcK0Z{dB;^SwE3xB0s??Q(?k%HBEKenwCe7w8=^#0+)'
    '-N(C^A71_C;V-X0-oN|s)0X;W?KmIv0F4654tyIY*r4jL3W6#Y=KnafaRuOFE=n%Oj&QAI6$8gn{Tbr$=cb}f{oYc7Qk&kRYVKTI'
    'NXnbn%GHGdf^#IeB$A3Kg22MT6$)zQ;eT*N0!F1k7s274CF$hZm==1{;ka-GOO~%G!Qm>;N9MveIXscxO_0zc<oCkU@SK-2T@j3g'
    'l&_HCbQkIjLclW~?m75}^OFMJ!}IqbV4#2}(>Et+dP1gU8Mq9TdiaZ_-==Hn{h6v<uhdX$+D4h)=HRyxep%j^@8z0&Pt)*p-!ix_'
    '(nds<>IC}oZ@L45;W~$_fd;|^N&lD<yr<kto!^yOoSudH;TM4%e%sgF|HkF_ijIn0mrix&_KL#8!fPSZA;r1<G2g}cUXo-wyg0or'
    '{fg#a(e!UruTFQ8tdq187n7t1KJ_wAZ|M1P;1Py*vx*j-DNQwJnJ2ACbig&$KULR@lcXyB8SZnMWo@%8(i_tAskW?TSwG<yS&sOK'
    'vc5foTq)Gww-C6IS_S`=B5P%88Jp4tQoxDh2R_VbH|=<wT0hoy_(yWh{DiI}Mzch9()w1O1n)NCR=*x@y0`}s(6%E%yQ5#>zaM@|'
    'mdg8gZ$I8`8QWF8N572i3N4NDOXb|?KR3FoyplgRg44Kl)Zg1WXr)<CYs$1|pDS@vwwuu@h|qS^{874$HCEVT+F;EBYZlnIW`S+%'
    'J?js9hq1mJ_g}yL^SjH2eNm;l;$bp4(@FH!g##vZ+RB4bTtPf6Z8$qOa^JQj&ui7rFU^!(+h)EqT_nTb0Ixi&cJA^?-6?c#;3%^h'
    ';#0B}k?*+fUIy~?oBV6&Dy)Ms-T|acAeI~g37+~+nqZKRU=g~YlwD^};0Ms1yYyj@nCX}aBDhdA4QranOs&sdu?La-ow5#ESr0*J'
    'u=IHl2pRrJf#MM?%KVlNf@6k$#AI$Q8(<b{NU$`5oeahz(VIXb0aYF}7)k$NxU6YG{g7t!kjOF=^+Q&M!PtSROmNl@^WA{ey$}9%'
    'bai~nbmwa>b5VCgAMmFCJuiIEG!N|)8B&ojG7SXdAwuW+L(zqKd1r~x%(H<XJ#X_Md*BzeC=^p9)iIbO@c_m^&!81!Zlpm{kgOZS'
    '^CR8y`IqU9INwQJ=?3w{MVF0+j(@q``5CBv7;?&ci0FBcuZ$pGmVq}6tx3Z#9ZZefQ$*=0dFbkfz&u2WVp<&DmUVbE$cYqKo@kW$'
    'Z7FYc$2*#JWTZ!(p^{~G;GGmB>Gc$rR*5X5a=(~CLr)%l*Y(@ng2I_OiOWNu2B~CfTsCLsIi7JiB_@Nn_XBV*`O`hMAH?VN0}M}+'
    'rKO85utbHFiSG1m+-5+Yw7sGmzS{I<kHQZ~+Wi-A87-2;*8lp6-7Oky%Ne^%p+yU9shqLQrj}Q6t57oUZn?-JyTWq&(k-vA&MB#$'
    '#!~!Z-7WZL?iLhL^f^%x?wE_CLJlK~Di{3rQDu#leT|LXEbL}sHw*h)v#_tVw$}glY3=wu-D!!y4acjMBUR+lPD#P~0lFMY=v6+|'
    'mmAO1lfihi&+%$R9iK;j`tX_MRt-ien=?PEQ@Pf)_vZUQp|yI;8A&CpxI8+PHHP}I7i~;FG9huvg2uB*WZJ$RZH)Wm{wE4Flx|AI'
    'zTCV)XyIHg?2Qe71d$Rp?v!-cH&&(~#bmtB$9*u@dLEcz(nFrwznu;K-Xh*e%}^{2mG~{2eCGjOGm~5G<7PX1B~Z3_Shj!1%Qu|`'
    '9ArPHR(@_p%5%v&EjCU}wg!`V(M(UqsXSW3C?@g}<6sZaG>+=dj>;o{^-MoAAl-7~uuRrjKA~R(n~uCGj<d6aI}0+|v$(gxM(q>*'
    '0@!qP6=jr`$qG$!%hsLi7CbxKH@8OjOPq<SZu!(zmY(eS)7v!JTI}u=TWEYm=HI7w)6P1sEUA7WO_T-J{C>gfnF^Dg4K%VPj<|MM'
    '_>-brI)p1}J^=L()>pDPeO`D@%jT&R35QM|&{EycXhL2@#7R$TTQ2{8piRz7UmWC%hxtO+I+}GNb2wYPyjmVTSbt?vHS?yE*n($u'
    'Sua-jN~JiBUR3nx^UVDYb*~=!^h{6AGgq2zWZ>DC?jPC9^Qj0-z-C5cg%-!<#U`vAuUYNkjAq{RsV*KFFB{LV9gnXq)A4+`&K9m;'
    'Ilg}}o==9p>ayDNNp9r%g!()ZRWHOW@2Q@6IM0m{N3L0SDcUC2RQ;;$<Ih^V?_0F`n$7pTY`$CDdpr8n6s5I8rb>&Aw22`(id5uO'
    'YDZKs%qm9Y(Sh9-)eaf%0Ee6t##1BGp>ta6^kniq?c<Q4Inmq1AycP-Sl_&1m`3LuG8-FybB7E?n2QaEla<_W>gaG@Ru<8Q!^xsg'
    'N%N$|EJDkqmS&&B$pj*R*_+bjEjMdqxQf$m(v=Oqxd>q})nshO3vWWQ?dLc>t@>4}I@Jf5@cRDY<*WPG@OQfK;o;T0AK$;Z+j78R'
    '9*D;0!lk2vkJ~>L_p5$mZ&m%4S^*iyNA|96c!!B^@BXj*haX?Qe)Dku`o}G;RT@T_<$7mYdV@-J%6D~1V?W$=;QyzW_xEq^{`~sx'
    '&G!!<?_b`3`naif#jdIR&7XgGc=I|@@#f{Le@}mHsk}Z4d3EJoiyz*Dh7~&g?cJvjZ(qLIQaPv9j_WknHOdY6z6RH>7JnN18CL7b'
    'SVEgz^@x;2MY0G!y}92)4A?R98g=;a^7Z%G8d+T_l_*6$j4JgOMWz|r26qW=?m-8Dg!{XPSAV&CdB1@MN_BORs{@mOL?2T+!XUbV'
    'gY`2$-)AU`9_M+P=h%1AVExF_%Z`=2C8E2}`m8|?<2>0n80TNuKK(=F-TMsbes5`aU6uplMOm&a#z^;knR{d3y*G;P6CUqAZSB%2'
    '+W~q1Df;&@-Tl5~J(hiYY46j~q^mEO?svM6W>c}du46~{YPo&?r(R?K^y$sNZxEJNta5V|VHH6+7r+z{<}kjm>_kA&hr9Q0e%eBd'
    'W?Ib9Qj}$1TI%D+3oS)qccew-{xCyJ=`{P&LdhIk`hL4FDO}FsOu>$QX;D@1!JxYG324DEah{{aJ_Rk5$homVJb}JouIAXHpMot~'
    '&2^(Pob5^rnUzo(QTHW<&vocBsP9XP)N`~H!(vxjC}MN?UyPf5X`!>@VllAxrG?LtQf$0^Nl|##ba{%gh#@&gOR;tLrG=6?&@J}%'
    'zO-;PD<kz3d{I=-&{F0dyVAnzP{IM~#8c2h`5Y}}{<SYH0?o;YK7}0xsyoM*A+%smS_CF|jxX^kXkl}96n_#@gq$;^#8beo(6iID'
    ';+EKz7KzmyUy5sFUs~9#zDW8MwA8M;p&OZ}phfdJz7#jruC%CGbSa*)eMw<r&N)`Rb^FpH=Ok1dhWnDDXMKjnX}K#cnp6g+rB-<1'
    'bXu`?4CighR79N?)2)axeFpDX`h0BXs!Dqn*bH%nuss=tk)(WvmcpD}X-SNkp`{3DUs`CDa=Fk_lw@C8c$M6cg}}AdI4=xHB$LiO'
    'zS3$@xm61hg@8R7LJ+Bg6^6vqk#_-d+ZML+O5VqRfBpXb-S=C_Ai$PcGL~Wl1+grL5MyRjSWJ-GBI&4#As@eEQ+SLyAK*!5f^?aa'
    'R0tXk*eyQTaB7itnH7Jzd->u1Pn%Zu6rs2R+tQk8D=qF9zWP0K=UQ7@Qd(BHw=QPj^5(F~j=_U=nM+uDsdm*i=^*oilBK_J`fFqG'
    '#``xff4ckd@b=}8cON$qr1%^`Ba&2(oIMVN9rcU(>>oJ)!{cb@9NQPV=*hHZE@J;Ce5NLRz9!C>YRYN*_@?;4F*~<M2vS9buF~t1'
    '&_$|ml<KPwpyr=Gtgjikr0Z4QQgb?DE5i(YPcdyP!;uOF9YGuD(1=&YeL9JI9}Z|#O+rh>>2$IjchDaR{^$%yA=Bf0I)FesF(B>x'
    'pQ$;W?AAq*6SfNnXuaNqg3&v1fXeaUh3#$?GmXam9=qLY=949IzHwZ;yk>!`qsN0WdnvjQZ0xp8=e+M!vt-q@rl@v0c(DT;qj%|I'
    'teQm>MNel(=7G`fL<S6aYDVqT>6hKEnZ4+c_4-D!33NwC`o0StRXl9z5a|TcPB+Xx_^Wvp9a6dn?deG0_n|}6YBi4S1WhT=Yb6Oc'
    '?C0$Df$gFXU<H#(5>_qmaJ?}H80Iq-mlK?9Ugh6`0Zi5lvbHnccVGao1BFY?=}73T0yYJ!?!W;7OsG7mj_kw%q3Z6}*UUuU38Evr'
    'a6mFv8Rld+4oF>1b4$&v2g0(?=g~Q!c(uyxcVmD?jLp={%DCuvVt`haR|)N9uwgv$|MV57Lq|K0!7f7~kfACR2x=!=8Dm1Li0e{w'
    'IubV<C2AL=1pbRF9~icn@5BMBtLbQ|IUQr%8OxaO!T}~KV>xiFcH)4fRop_UIUOyYbpXEa!U3tO^>7vUGKa9L9iFA;bS!(fDPtdd'
    '2<yry(SA1u=xUj}RGbd9&+{a|Py5Ma_g-1rczgyBFvjUj&A4}trSH3N0Q1UEtJQ8Cp!J&HZuPR-PgGird!I@Az6<AB9lbT=mg$Wl'
    'wwDHQ!m7EMM?2X9MCmHxz0{0*dpLdHg#(&bbZEL43{u1^4{@oP^s6N4`yL#i&>P2@r{r!7AXSV}shIW-yYzjR_ETEz*>_?uG@@w<'
    'a;9clrbJ>N6rik{5lOk1V}x>CWicr=179)&()V2$z-6_EK?7lV#f}=80%9BzX<IWRZX-{Ac=_Yz6UBj?6d^f7P8XY#kb%QoYBgID'
    '5giTN8KY#imIRjDfiWu0Bn97-F<NUiLrx+kGe+#i7=~npni`K7BU7lrt{MYI^$an#-<y=a@5B}?$AlO(a79>=ynuW1gb*@AOQNGo'
    '&$b&=h^hyAKhhPRbw%#U7Z~rz3^|FEZvM3!W2mlNg4&K4!!qoOJsHEQ(YR2PD9L=WyYYqTDsDxG5npIV-CY%i<Jv^-$w{Pi*(7#j'
    'jKH;s^oTJe_oQ7FM(}D7Fylc0XL5E0JPBeLlS4-2psY6gl2d!wim)u{)kg28HnR41YIPWvOvF1YjjFa0n~|w$LdLvZg``=<nxeu<'
    'eY;FIy9r6-YH>ijk&ryz7xFmbm7!U>QonGE()WGX!eJ6jXLL8|ZRfGtjS`rO=^4#UTHD3h>_<u6oqJ75T9R4fb|ZvfI!RP1QiLN;'
    '5ul80nn8cOfB4~b%JtVJg1dkgQSJV@Fw*iCl%#m)NzTU<l$N*Wo89@sD6S$vFAI;m1tlDz$&o=cMTId$@$OvVx=Ma>VRYIpC=rTG'
    'v?Z_1?9UT{RTa5+VT9H#D1qUnro;d(A?(f(u>7k8hZjX`-GUH-iJo+w6g}loKJ{&1rlb_x<2=2WMRDDN5=pAmhn`}aedx)SG|85X'
    '%!%EMCZSZ7W~z{rNa?~nu*Gzbaam|lE$w<XFh&@SQRF+aMIu~zISMhR_vWVW`>-W#sjNIdqY0vMd4jm7(^BDz8pB2gzXgL|?@Egn'
    'bF4{h=`v{UWm76F=nPj9N3xa8b|Zw;zW<E5E@5t<dt+`2ksGhkT^K8K3rg4#Pb`%T1-Uy<cr_inFns1Fgp9Ek=0vg#Le?Zu@eHiW'
    '-8wRi&NI~5ehf<A_W@fa$<(f;X=xw25BvYy`?8(aaU{)mnd`v;_vJE?b*510tfezg7El+11VxEJ1C73!nah6niJ%sX)JEB|y!>`8'
    'KDK{JjFrJ)@Qbrm#p2>{d?53>5`!Z~qDT@vS$CO&e4C>@GZ|-<5N2jLzRUCA=X1QRRq25pJDLqE%u$}X&uX!e^~_+ZKIwGYBxFqz'
    '_rt(0DeX2}dMaOxPN0$d;Z$7;3_qX57t3u@x<_3zFs8<>2Pa&09%HOYw}`soRDDVgKA*xEhF}=UNaRRkeB6^cQDYdPX_0L=nyL>g'
    '<w**|NVbO;Mr^5~A?Y*O!gz8Hryow$MY;I-B)%}CvIaFAE6_ag^~uvTBO)ztxv~=Oh>^&2XESoeVhZ>4v|Q{AmNcrqt~&0Bk!UU^'
    'x}s56<oUW{lIZ`+in&7uqUHefFoptajtFhMYl7H!)-<jSuT+PdDY_%leLL7nbSQHj9$?jhgKO4zR_xkxbhtTvlSN0{?`zY(YuB~+'
    '=pa;8SM9C4=K&3E+YFI*!0ZY>?hSq=n9zC_AhKuNdEi$9QFvzIXZ_jukT4WW<Q(E(uRrIGMa&|Q_d0y;SoCaX4i(Pl3-)H4#e9{I'
    '7>nd{K1el>7>lKIIIDwCJ98|Q&+3b3j~I)lbCA*%eZW{4n{A(>*#q>2(*(+Y7St@k<&(aWM}Yn9#hd$IKmGE{AHV$cw?FOTw3%=B'
    'LC&AxBsVfC1Q^;cxBM*TMhm?6ufP4gAC(P8Aq<)A3*#Q3dqU1*h(BP?mvVN>??bwChhpa>)JK)44n>LirX%hVV=;7&FRFTgwrD!r'
    'pg@^Nj781`ANmo2kT&y8r`XwO<}emR?c9Q*Uu>N_7Rl$liy)5}%RKnKpbr>}Wr^2a3Mud`4W5kdLytbh*nyaPP4oaPkmVEhQjQ~?'
    'u6I2?ts)`xs)M1we*fv0zeX6>@@Gp*sF-^;0=UJ-*<5*Ll>|`<j{jj0Gr}zuoBq;%U#LaxX#0`x4R2uF*4kWV1H^FP&R_w7)3K#F'
    'Hv@WZo9Bc-Rk|y=uw6O^V`1WJJSxPT(zIgOq}}rXk(40LYD&Gu4S1@ZHSj&*s=rP%Wos3i`NY1o?SYjBeraJ>#N|n{YswKDkt(h$'
    'gsDyA?{;o+9bC^qMc>d5K3`C?V|N-%X;an(cKv%VNyY~Q=iMV(AgHe0Yn?Q#Z@b;#eVt-)>hIrEwC>B_k(t)%@q3VhQj~(%A-EGx'
    'Bpax#>ROWK^7oZ#U^NT8^@vL2RmH*Z6|7{v6t=-lg_!-Uuw!U@V4%Nicg7=rj`ZnDVXcG}Ex*{zr~|wPu22MA523h4{qO(y6Lt^Y'
    'xf1~^L7SfX8Y?U|P3f@eXsk*C(Fej}X*ZF^bUk*{?`NCSlR*`G1@6_gS8cNE#b#8vH-y1xI#us~?~R~0ojJwnbD)N`BkI2w7h`O*'
    'UZ(xM>PPO|uDM*a@73kKy^n4`hwggUv5Jqz>1z)!K2krJb1r<50aSNvWaF_9#zit?>mlD~jO76@+PVbtRbO=Kl8UsQU;V_ywJyEp'
    'UGCKN<}P^RYInTM%zfA1pHhyq9^@tTkUNc2mWMFQ8{GCL#;`H;|I(D#Pl@?dInK|G-9CD)VG<m^O((;>FIK2u6T5*)Rc$5)3j@V#'
    'CtNPly2ZXZfRMtA8YUQxv8$3WVN&H8gaI1<t%(YnD~Z+q8h?i+N*nRQ-@z3NY)XlBW$aa|y>4yNIMzIiqns4sWPgAznXpN^x#zy='
    '_(i*x86ERX|Ib^cbFD1qbzTfIDsjzcxYS*pJq9UWB|n?s&G)S(BnpJVfBFz`+d&k)glWA!MD%Q-n~r9@-6g(`vAIV&(HJC2%3^z7'
    'UW|coGh+-Jyf(L~cF*x#WycaoRCz-JO1y|_OJJ&==@}wwWfd&>qfZHl9}3=vX`#v(tqY}K87-MqU()M?-$?4Yde)9KUC+AxJ*?L|'
    '>CX}qV*$LS>y|t_E#5Wk5ESN418kO&%}imwuIaZ`#;#b$tRBw3F!PEy2itZwzD4sXgud^q`Jl6NT~a`SF)fIiujYJwsZeg$`!V~^'
    ')cbXHI?pP^T=y8M(ebo>(~e9nRDs;t%Re%lff;m;nVa#<I<xm?Z8H5HvwV+!zfRmD(;dCO^N^qlj0;`JM}tdQspMP_r?CRhhAC^D'
    '{;2N;&%yD}b!~&#50>w77K}@M_{?E>533$z_K~5t;M;%sx&eqz+imph9qF`L2)*~Q|Hd$6EQI$AzfE%FsPBjd0iwV~jjFYd;SZjE'
    'VepOZ_^u&L!aSC^O63>4PHlAoCk1&;mA7fz(Vo>Km9OSh{w7frGJZ+@#{!wE`;mfpl=@qfM%rEbA&E<R%-P}$D$<3(lAEVjc^((q'
    'UFV8)@3ebo<K5^N)p^8|(KGDba`W5lr?<IzG1hZ22qD+=UMQ3A>B9GH{`<GF7ey0H?Y?cJ01u=z<^pi@1A|U2V3Mw)#FkSrS5DRy'
    'C;n|CqnJdWVe!ah?EGHT6(YDXIvNY&Eu$mc&oDDxI%CKgFyq_ii3Iv3irIoA^*qRJJ$Emw=P3YX&)Ln~`yS5UsNQ4#=j!a<LcMv~'
    'bgXZ|Dqy<R61+#;=1{cVwFbY!k=1h<1(>ig1obK?@HvO(;VG%#*V&7#4RR*{)9!yRJNw-NIv^uI62zI#eoM8^vldD8T%+J_8w3W2'
    'uBja)d`Dsa6(|bUt|pk$CCi4=%v{aw&LAkZQ`=Ew_`r;(njC!dtYodcOB7c!esQfl63D83&|_1gy;#q)gXECe(6V`k^^$9%?U5l7'
    't4(Ai^WA&Xy$7?9sEEZVFQWA-nGAZ)ZihrWIDg|px#xe*=UyI@@0*417v*(dW9hZwJY&(4vzZ3pb6Gus?+TZ28s~R=WSXfYwfeeY'
    'l(uv2+s8|0Q<zzulL0+6j#|s9zQ>~3$OM|IZ|Ob?-0**hQ7*JpHL$;Ijwmb(hakFo+g$`@iI`*Vc#@da^?l5@x9Rv;1n-##wP~k#'
    'v%GC4X#8yBu8maiz2-Vf<JhbyJTmgLHp`y=Wj(wmG(q<489q{bU+m)d31qLk&kC1&vE=L@i|H+=0WEmC_fxfJGiAG3-+3XJDhyVP'
    '$F&&>tIc27-6d{YVZGb-X}7W6_{UiXcIKL4_2$;{Eux^eO%Y>(?9qSYUq%0=O)!lb*`DVYBG$~dxd>prMreYdCvHaI-e-->KQf(K'
    '2g>hj2alX3lt_B5^eo3cX1`X}Tqu$Qg8vcwPc3U+QKs`OLQ^?T9bun}I5^+ck;kKQO2+aoEWlgXW{Blp;n;G265e>50b-wI(a<w~'
    'w9PP|St=IH?UpeX!1>z?%PMuAbr_ad2evGk+iQ+{Jh*O?xXC{uhs0@{w$u8d8*%KNEd(N;8QzZ!#FXqtugm6uJvjCtBiYcZ^Nhr@'
    'q+YLTF7q3%>QETqs~pU92Iuj~JlM|cATUOlirc1GJb5W6pxs?qtSydJ;IY=YSvWvkC{XX;xMWFNlOSgHLNP74`C8ajB(&S@X3YLm'
    '!>*gu?KG=0Bt36tyMwHgVw*Njwo}(OK|tVIVq?7)b#0+6s?>JsH?|#Y_s3>fk2BA%I;cg_9AG{5gREy$sm`+yDv}6V^z)93Y!8})'
    '2uwTq#{pMh!V>pl7pkSu4G>(9K}=o8tc$tHMyj{A5t}UQ#btiM^*!2%o3)XvgmZwsRFAQjCAB)wN-{u&s&4msz>tFyagD{h!z<{x'
    '^jyaMG9|W-4W~_slcJ4h8HM7}9jNw*_Dwd^ytB<97VL~DOpCd-xKFr8R0mi}^Prh!r;?p#L1`}~Y(?2kGa<?Z>)9$CQ+MQ%PE+$J'
    'Glgfu<e{s7{l=?*BWP0Q-?M#`H=Z|^9b!3P@vk4W_+L?|^9&>F5W(Aax@fhsg;Q%+O<f8<)<CN=bkkx$m~9NJ*R=px0MZ%uZXVRz'
    '%l?~TVJ<>=%UyFLZE_&nceu&mUQ9PPNzA~-^&f8O$f>KrL-Ht+BmKXzZ@h146i=I*sLKMwt@-~QLb+Y{$09g2SXxx4^Q=PYL_pZk'
    'vCT`z30GnPPyBye>BSAJSn*G%dF;#I9~vEzcaDxUOI%XV{1I4~nXSFrDVzgl2lA-xku|kC&q{Q<iN(8a#vNB>)q$eo5-(hQR!p+-'
    'N&czd?_lK1zHZT#Vgt?FG+!loL#&w-JvOqov5~cC8(Eu6VeUsQ?y4@k%zo4`{5tt3SZm;lK9>JgEZ-*m=LXTE<r@lwDEYDcH@19m'
    '_2b~o(vRtX71Osc)H%_k>1&Gp06vrc8=Jl*EZG)y<YW3@#PluETF!}{J5|BTTA7dGzp>#{mLN&m`eXQC#qg<0=lps!=gT<f>yPQb'
    'vFWq4IghPArvFt;p9!PqM31H~VvbLJO#hut-zJT>ZSyhxuVVU~8!;z(G<_bEe4knWolT#o+uzoHO#iExzJQ2tPV{K{EC&3aS^u3)'
    'U&sXb#(nbpU&iz$p<+(-X!<mo{wK}%&ZaMAQu6HB$MnC9>08a`M31IVV!;0~{dYEfl^&$C=41L_#q^b7c24x%DHrG`+<$Mw*Ni3M'
    '{-=ib%NV{^X}CA4;dM>S?|<g}w>JGW$LBwm|5YsCaHZ!&k5hh4Kgs>~w)+%3i_|=dO%f(J33Rtc!k~Wp@yDP4^3U(T{_)$7pML!Q'
    '+n&ML6to#t5JyA>v7lF5cCx~#TgIf*egeMb5NVt}okJX~N2CnWI3Pm=XYN5Pf<Y;sjLNnw!nWESi|C0gqQs^w;y55dIPDoE&Snsm'
    '<H?n<jz41H&zUO3l0Xmm!*D<s?wqbZOeFiuz?8@yY|8iu_86Y{Am)HOP4h7B@U-_pXn34{v02{(xWg68j0*?k3AXfj5Q9Ww?=`1Y'
    'M33l$ln&xYw9tlja@2Zn<F!w$`mk6PWG$_j6E?0=9j;P?@T!egoz0@vk0QKYe99pbO{&dn@iFiBHE$`B@OBV3E=4URL4J(;y^Pzc'
    'WTWY`$NXhXU5O;jwxc~}=i?sp=lJM5o4zs$)}#|3)Bh@_uhT9HgXnRVuP9OWWB6}u_*x~<z`?iq4D1T@fP99bROSf{j|q*2KP;hP'
    '<T&9Rs+K|673L8PvWDjjf)NSQ=!Y@Lay1s3WHbVX_5g*Nw+<sh2O=CO;z*m1(ZBADVNHTH(F;5lBsvThYvE<LGVCUek21XaOhF0P'
    '<DCi?+I<1U$3EW?QlfRfuY@ClnL<3u5mK1ElJ&Fu1kqo_C4%JVMGr2~w>8?IQq6aEj@TY!EdS5?`OBC-lT6Kt9^sd;M*9P~_|}GR'
    '6Th!NcK=oEo^v7QM31YWwnY15`R{D`JVD*F)HP8+-Bu_It+)hNRx4cUvaY=}BW>T@wqGN|e!AFASGRqFW0yLSH_42+9v@M^h-VN~'
    '(>c{Z&rsu8Z6{pSdWNCn*+*@@j^_|6Ntjys2^zkNYmg*4%RPu5U4xG>4xgamolRc~l?099WBOml^lb{xA4aBM#r4AHXxBTNz7lEE'
    'O4sh6V0Xm_?4KxW^P>YeB2Rq%u>BLA)FAQx+>(04xg4sEH93PUp6z<v(HxrW{d3*&2V1Z`fImhPk@H8R0?EfIkfk)K)!@N#4J$6z'
    '@`tM6i1W%4CM5S<fnUXAdPX9=RzFhw2lJit?7r0@H1SFrJYE^BlXzt@umAqHKmH01;|GxS*T4UBm*22b<cf%72~x$K&T^vq*FaqI'
    '3gI$!6q36n#OsM=;0}|Hr^M+coz5Tq^R#hZ`I99TLXY(s$I=%yC`G9!RKUy()AP=;jHZn}!%@b}@WGkxxEXv#ot_FL*S?>peIIuX'
    'LnQ@SJy(z;F(84@loyX9kE8aCMB7=82&01Lm=KBWB=NvO(2Idja^Ap|g$$LE(a$=?>aDQi)%tm2AYkMSTSvW~)m*RVHMU>F<co7k'
    '1KFPWIg`i2c*ow)U|2~(!QhT$mo5}-#!&d!bsjs7;#xq&4%`Y?30f@ZK3%hkH-70#;nevGi$%$KiuAiY8^L0+H<^!W++Af(Trf%w'
    '>qVPHvyJB32j54t&NEVZB^v9c^-SR@bP%^OlfaJ=HFmC5U3t8c$RLIG;7O&xD?_L?QhWEPR$($kWc7PGl1D074ac~)oV?52q1NJB'
    'x|i^y<6A}H$7GEgxM*O_G{{s~2<ss54pQoxd*-RL4lXw~Ct6#=#~fgliXl6%2&)aSiwcKV-d~nnr8#XBWu$5lWjR%Y;q}xlE>Q~U'
    'JzRubv7`((VEL=LtT7e06vtHs$!O(y?SruaXsvQusY%zEm9q-3Y$TWQO1KQKyt@Pq(VFLLd8DdeVwTf1{M&3TF$<|ZT7E#Qu}R`0'
    '@LG(M1fW+6eMF@Ur`mIGDX;^G^*OPP@1om|RA=F958kDrf?Ch<@9|3f-2?G=7o_FcF+LO|Qr8QzoVNZo(75PRcT#<{K!Iip|4Xwz'
    'b}Ud$ZJbB~3ylb#SKPG;k~$}v%T76ai>x7#!YhS?l@92rHq8lHAN~ynEz$;0G3#S5k}M}`s0ENjY?x#jxyMQ{601liK_14lBBLz&'
    'AKSnsFfh$v0my*ZkP{0oOQaDkm3XBK7Q13`Ct;dkXGoAkoX)bdY&w!POpE1Y4J%!-CBs6350@d=MkMFtT<9`YofI41eXiTj#S-}G'
    '$B&<W{x?hp|N5hRJW?5wb03Fv;eL!bd9<kRn?fF4Js_LZ3Fi#S8Fp_5X+l{Zwx#@-^6b7G(xB=*aRc$`gBySqgU6Z15aWpPoCd`p'
    ')MS=-_QG?XM!$!jo79*ZVjbQ|GT9KA2dm1|c&Gcj1t3!CRlVG#lJr#duYtPED;Pp@cQKK1Atw&^7gBScg7CFD$5iGaN^~sEma_Jh'
    'vEjOGO{=TjZqxTae*edx;B6NjGzq!tCN<+aoa^_rP<bq`>n3-6II6Q8pGG+2F^4ja<Q%&@hm@eX38ws*^6btWLM2L<B+c0I8Lk2v'
    'DU-oa?(xvR!4TVu-tpx;?Oj9=spG3^W${iL*iMD#K|^@J&vAU(=3s>xlQ+qnc)lR^c)nD~g{-)P=d(O%>Tq#=W2uKI(?OmhbA5Ci'
    '7aIIoY~^gvbBUIuIj+=+qdP#xd)(Op#(N?w2kTa=dTq`_p<x=YI_Y-{?gsNmI8`z(;2rLyxl@<ogA=qGNMN(F9MhZyGI~vx4GK~}'
    'jVujiNz^)xAU4H0jaRDq<enLF3S+BHqobW7Ki+x`O$s<0nk{q0xzoL2l24*|I$7t4^QL>lX%gAx9LYI$cMjo7JLizdr~8y=cjk~V'
    'HcfZLr(ZS!d=qm!I#k|q&nn<)1(#brtaHTtbWcTRJe>(SSqHomYaDe7{<gO9;K><|QHm7Ghq2x>(j>qaqq%{vdB&Lg;ESG-KFUKX'
    'Zq_YuQ=StKImoeWMVDxEq0H~#8CAlEhGd?Ro$ML4l#?AsGVzS;M9*lb9GgVWk(^_9=a40K;u+b*Gm;ZMqg5&k9m&`;TF>HMgK&*-'
    '!m}U)gMTt>2G7XmJ!5TCH{lwl@J<1274M`fMe$B2ct%Sor}Hr*NjxK4O?|M3$A*^DWRD`iiVeGixTYmw{0W9mD_L?Xp?LVe{p0&D'
    'zwA~qOO0Cf3Y$7M@z#TGm3iyL!V2~9cyDc~Vrswe(11oX$x8WJ#d*4`M!#G`*p(vv^WXQ-!MM!mPzfFC8I_P3X7&$ynfdBL%;#wq'
    '7e+1<I^;7lpXXkyWX#LFmk;8-Nbx6N<RYO%JR|RgW&6jx%zN=5-e-#&7&%SopwGyAT&nCJ^fL45gP5<lOzR>;;QB(x_|x++9~MV^'
    '|DYF{AG#Fj>CD%hjxCsW7TAZav^&*!)+)~$n(ubukkUmS4(hB$o;5nDWyu+mGwkjRvYO@rZ_1A;&+f`0Jk6PzLVWtL$b$$u7U?$J'
    'R@Py)s8%rmcl{zS=V>31H(C0tF|5Hm87Xj=oB2kwa~63(q>*w}F*nJatTUQjS)o+Og{(MyouLRzr%FmQhrv&E7z!K8O*{sjcnp4;'
    '$4~?oFyr|w=Sa@6yK_j0iRSW&!=NWR3}H<gZN;Zww#SKOSo5YU*97Vr6OLmkxUB|<!RH-DP-#|3!74u%I-A<#orv}I2}SggNC+v_'
    's$OoAIo%#tdlD0=kPBIH2Zy1QoKKI9r5>V8UvYaJ2o%ZD7amgk=FQ0-F$dDl%2eYw&58cdhy+<L=SR-3yYt89+dC;YrX0I7e<0>H'
    'E7j5s9td=}0mLgTE3O1@umsrlMgF&&!1dNmNm>kcvF<Su@TqxG>xKY7+1wowI3g*NnOY;zBX#O|2!xr4tvZZN1uO(63i}UU-k_K?'
    'J8a48adKq*=~<ErAPTjA$crfjUOyzCqbMh7bjM9XhIvNLbD`P(K`-;(Jc{?0rE77XY(#MNjLe61wAw%DW#+2~F<%lpj&y}f0~=w_'
    '4FsuTEMFQ6mxqEls<T2tY!Ni}4LL`0j@_L@83@gkA5)&)nL|d|bQdT-{jxU3gCq{`p+s<=Y1JORcBEe$=REBfk&2}uhpv^53qq#q'
    'P{D!_C_HIxjAtF^t8B-_hDgdw28{@Nl?ri8NrWDXLSzag<2kr(h5?nMgAg-A=!NKXS}`rD7V&tX4<-osTh2TR@x&DXyif8=sl{yS'
    '>?F~l*q%g3YO#fSeSE~ph!xpVh;>?R$18=zpxv5QBN)?gT>A;Mn(8D-N=KCu#ygpcmJk#uYmv}1|HQ^t48PRe`i1pFx{6$U!XyDR'
    'sFrD;V0Bo0LMWjjPhl`oPD7ICT6{vDB;G?ql1=4f+e)4=&7p3O-OY@BdS{V4uYxg)qA|PuV@}HMk~_Q6o%34Fe$1%gf~=1{scBps'
    '`%ER{_SnVD*u`Y*Sp~ijsjd{!K#OP)`)Np~zGbiAuGjbEVAbLi@?(j+p3szVXXen}wuE_!c1{mal}k1`s<g<R{G>JGWge|~@@Z$A'
    'eZZM<(qU=#cqT;Oil!#v#Sldm9au_(nVk{W9l{Kzli+eZ3mc@1FAbfI>smP*aR&eGXs6IL555N3Pg&n-2btMaD192wL^0^{bmOAe'
    '`kCK~X%ow|W!nG=ZRuv(5wvBS)Cq0rZ;Y-z%?wW)(~|A*rnDrL1jTnBk6o;cUEDl&w><W=+WMNYXJ<x|v8TUXGxqGfMLPE6Tu-SE'
    '39+n0*~!3^7J4%+VwslI4;*0+S!ODsB|YhV#M3eeh4g97t(?o?2U0EIw`y>Pdy|Yk{jJz5@@21>VaRl}6i##3&iXjZrTO?I$b&FN'
    '*71-sRSpmP3&RN>_ICqxOdjqHF+kG;4t5z7rsJK6#D$aRgz4Z!OQ|>~gQAR_hfW#OoCTqBEpOm(<nn3q1}ZQ2NtQLliP~W)n{-q<'
    '@0lmYy8yBr&@l1^PA^N)Nih!Y8qw5vClI5xjc2uKe8oo13yec3{BVLyH3W)c6_jLCg(qR_pt?n2YwE>zs`>F@t0qj&7YdBEAzO%='
    'H7$>5=H_X%T+?jZGd=I;8t}gePhx5x4~DtWxEjPQ2Q4S_THZ8i&eznGM~Ej<DQCc5D(TQ(PR#jgs^mQ6$(ZOYGxAC<OEWIlK?XLx'
    '*2H`VZ?#~)EIn43gl|`RwmX<Hqbl92O>%<Z>^Y5?lQq-vv^rRQRPzB0W||%BPV~CenZq3-wrL%xvD`BgT7y9_TErm@wTpUmhPpG$'
    '(r6?};t~lK9kFjIcY(oBy>c-FF#tT|>D&PU$EUW9$K3HwH3ZiI0j<3-C-3KIo&rD4opIf8Wz$OcW>3N;U4`v*cXv>E5Z(ODHP(VG'
    '?fz2E4&h2ykCbd$_4Ew2+vDugoWYfre+S76&GQYf3t4j;EtlUfsZ}PkMOD!j!qs=8MR#J`cbX=>uNl+b6U16h;p)@u*QR@(B3k)9'
    '{wmAl?Q`LG&{`?Qg3=md&GN{pnavjT2phB)^(0F$<F#+R7u|I)wsx;{9dzxu?ws#1f@J^#X{WoT25xSG*e`jCm<=Wzdo^(CLwh9&'
    '=al(?8Azd5I^C5MHPra=ExhbPau2sUqZwNW5?m4_h?fi!C|6P@KzSnqMRJVCy=2W65U6N^R-G2c&ecB5O^1EXd0(x=6Hcti5ScW%'
    'O>z)K_~pZ?TTXT{F+URwKBdEk>4`D5hHY+xtzvf1K+vE)7fx%$;daf#5A9H?AhH#!pyivxf4(ChK$cNjuD~ucsbUTkCLkRVg1wM2'
    ';~JhpCWf0elwDT0u&h#u3L;t_0<60sY^cZ+3?Az#%qkZ2Chwn7p)|1>j&};|DPc(w7pmSHOoY&e1q6bu=rhQKPR_+=TaQ~B^^_uE'
    'JZsmLA_@k^Vz!8zhNDQ}{{!M8RO}f<!l+OyNExAnkbo)7*vhj&w2Xu2&oFqdCX+_GPTMqxr&K5|*02Z~VPoz<XiwuIeP0P&PgLR='
    'L?SqstKf&5=J1pv5gD9vdU_%>inq%~13t?$fha``XwuIh63MMv#fjN8@~0GuBI_V4n|AV?R2iXGYfCqE?J3F9ED0sKYFC*%8{PNa'
    'u6I1yVxP~MCvO<yp>6KtIE*oK<B(Pbjm?uaBSOV?$}j<F#Po)LDZ0>TeyNSJSQq;Iu2=eUH}y7G;z|d1Tcdekv7*Y@ITnu^&D*&~'
    '^F<=KlHqd#L&lB;kvEfH6Mz!rrq?OW<)bjP)GO6;wZ&%3ShLPzYaGKl!^Kx+9zSC$mG-L5tHV^N<8)cq-Z>yZ(pus6Z)Klh>_*%5'
    ')>E6Tf5HhwDVz61PHUO0V6m~2Q@n8!zNIvRTvzTHWMW}nUoG9)RH<i_iN@YAYc(j&#pa{lR1I!&Rv?cUsZ>uO6YK=3S8GZ(Rq82a'
    'LM1orThCikc}lWa($64p(u_NzbFbS449AWEp7YAarqk7=Rk6z;2WqKf6<g)nE1h@EDc$NAtjh$=JEAw2j_Bny4S^e5mXp{+?a}gM'
    '82`(B-)88a48B|@bshZ?0cNais?fI|wL_V_AdPQ0RvUU=IT4%ec^;$y?ll6|f!=~4tGa1ST+VXU@<0$N!N)2>8|>@{>qAcaDrO#x'
    '4qe3MyC>ljy>B$!8xbBA_Tr3X83^hE!qOFtrn#Jr@1srlO=gv|9ZmQ-i38Q-fM)z3>(1D-?5ur$G<|qrf9$gB?AE{Y_SI3vL%$a_'
    'w}ofs;?68?z4I0yClJCfs)`|@=KziVS|+DXq`91ENq<>*^~%tzP_Hn(a*b7D`_(tj9xG3;ioM#7OXl(SUJZNYofAiIyoU9MU3eHj'
    'FG4clb4~ku)z#1wFWR%UqJ6I}@9lkb`#E&iyN*?SG)_=Uc=1v9U$CYNLnUsYk5zg+_Ca+?rpjci(Cda5%3fusgZ8}WdSLSQFS=Fy'
    'F#lrLKQVP<Gvk?aYnKA{)V=k(H`cA|@)%Qhxb^;&a-8)i&;Pn>sRRTV5N4T`c!XC;IZQ!3LTnvNDm^E>cEn!dk(if`lYq1}wq3_q'
    '!fwYSx(e8oolN5qUU%_`EssZ#qLO%o`w5)M*N#W5u@i)$rFbN&&1^i9{jw2{^eWUVOs`yHmH5OXuM&@-NqypxPdxI8M?Ue${3H{b'
    '>t&f#o#eL+jqQCco<t(BKs8m&1$jBi1=&t<I}32SJ-Ebz!n57XkSZqoiERJw?s+Z_&$oH~K_qWTbd?j=zwDfKUJ_k&FWE;YynyJu'
    '`63_7vvO9&<3Ey1T0uZ(Vb%>mvdT#|EIm6RfSGtDZUxfDBScm_pm2XV3eAPd^OgJ}#&Vhl2f((DP83pmxcG#YOwyGz#eJ`%psjKg'
    '+qqJQdjtOQTN_*{p~dRi$<5I}-xdH+r3A@(dP%S;){BJKMz^QmYiTUF5m&nk-H6ZiuLf^0_L0J<3a@lZIfKDt1(7y8@q{xBKu!u7'
    'kvbTtXhl{|-4M?9R4zKnopc{9Qh2-;GIf)p8CN>8O2yMyydtbNo+&C^Tx3tSK$K72r1aY1m4=6=#*J>q&*`!x8O&oe-&l-fU8<am'
    '$r`FY{FbLIB=~3<N(L*+q|Uy$qU+c1|Ni^;-+uh@^Y_1g|AEyezx?I5@|X#Xz-XH)Pp!sf*WL;fn{3yTvf6X3>&Jc0noRZt>#i23'
    '|JKP^q3W4#7|c3e_!_UgyYeWYN=zI<B<q6FQ%u&dEm+T=93E9Kl@WZj@+fJs(?aS1#Mq}d6e2>4{m7^YU@6+_Xel+#iRG5~u}_zb'
    '%6Q~iR;Gbz8@{hkMXk`vm}zx7l6P_H<>U?P%bv_dr@oW$qh+d<g@8VlDNUSua6ZO#6;Z-K@WCr9oCTuA<lJ!RW-#6>a$UvBSLJGr'
    '?1D>NC0H<(j%PVlZBBt-v4&_mjj<9ZUry#Fd9^-avuhb}w2Xm#OVcG?o1g24JOi*y<_@NIsgt#XsZ#*=xjXf#ynR6J*N$ll$bRjZ'
    '3eh@B?!=FxuJ9;u$(Y<xV=BZVDHu~B7D>sSCP3(OcM=8E6{4CHjA;rxel5qR5Z%{|>8`soA~v?=X2A~`LdCF-ot&cBJP)q3&4J`R'
    'cnS==c^-UuqhSK^eA~EE0P5SuwG)VC{a*Yy8h4(>Umuq{Zd^OTW>&|w6KrPvUP+<x*1g0kjXQyBR>zeVrQgQ;6e-}^aosV=kG_f<'
    'PSXC5!HxlSs@js6l@m@$<~f9T4JJElokxs5OA1qOW2tCWSthYml*==c!a$TI5}uO->evgQPB~Hi%Wr0d3&}k;?2W`KP12MD%#EYv'
    's&y`|y|}bZrSNDTV$%V!ZnCtIUAxu33|Y6Wu#MMMg%ybKyOSqK5E}%VNxllnx-3)6$+{FW5VcW>Tt@KGGNcll=khgJs|B>CdYYVL'
    '9Trmet#>VU6g85gs%vlTDOQLr0hOg|uvX<nU3Sprx&#Z!Jz9cTSEKF9-rCZhQNt#*n(lM=t*UH<$zu|3S9=ck5T^(b#$}jZ*<0H|'
    '(`9#^uFJ2G+N0$M<F!`MmBj5*HnK4}u@&jc*t$7hE7hUEYQ?PQKv2LdLj}P`xO>u1d{cyJHR%nMCUDEi>t6$zi%GwogdZ(ag&o)B'
    '%0|x8?nGlJB9&=qqlAv9m6VXOmROpvs}nYIfF^L3maT8(l#?}xQf>t|g#;fiLIqAGgAWsRx)~?i<YQG)XFc<>5f}wDlPEyf-5R{h'
    '8&IXAr*XCQ6$g?m7YOtpx&~jkP(Push4`l7foTu+DAPLKoGT@>e+}d==54QJz|k@W^0Q*reC}MD6PgM9r3fh}z*tN>Ls^MeGI7$}'
    'sWpeutCh*KoT#C4HY`^=h&|*UE<w#1%g&~!5?mTsnC^PoH2M(+R#kXqBO;qB6%5wz++Bi3X0t~wz;c>~El;}@{S;Drv;ZMirZQ{9'
    'Oj*)Ro4YowhJX*-Di~=Q`kye_69jUSQa?(3TYyCxioi+?!b1d4gWu06^#kHGgY{MJUL$!I==@^xMpD}-_S;GL;WE`gp_y-&G)|*u'
    '@QJSiL@P0MrPAJ4qkd4$n80NJ;k5`fbUcU9%Qg=mcaKRCRWkw~N`Ow&aE$fcZ)l={Gn-cP0*Vm{Ulb616rF~cdCceW9$|(K@=}^;'
    'GF-C@s5MPMt@#UrT1Nsck@LP}ysw_^*S{8lg3ouN8k3Zj5xffSIueN3S#p-ZakWNP1@cM~6!6~#0_|9WNpZ?cNsw|jIn-!(SKSo!'
    'ekrU3DuAdjthy-}Q(+}g32Z(;>Q2dgb=#fF>QY2OT}n7?OuT4J8+W>EHAyrJY2}hx7$VhRx%*2%R(s3rEKT7DmVn3uOH<ZcDDdO%'
    'mEv^Wc&~ls5n{DGA{;m_zH3|y_qt<A0~(A%%*}W06AT1u>^NfIwMA?s5R{DVZJVmr2#iNn)bkK%(iS=;of2P*K9%Bq#!aMAuu~O<'
    'P5iK8Wl>N%TUO3na;L*u3uX{>qdS?=ov2R*|KiOGqXJnuZ8D|$pr^S^coP_t&ESF`SYIkuYaI90UWx;2FIOA=r7(0`_o9BaUh>(S'
    '2BI=au4uZ6%#z*}l$m%g-!Ucy_ECk&9`Rqoq#Us3>F!4Gs_RjJD(jg7%fSP%p=l8~?!3Dpzrp`t(0OeKOSQO|yo+46b~knse(df>'
    'BwI}S2(rySf^KaJjR-;RNv2RL@W|Y|wh?UU(?&m28$t5WDGwOJHGlptg5&`noC=k9eWhybz#a9m<OvU}BW6IOwZXmCFe#4#0_t%U'
    'P;EjiY$7gr<H0wIipRr?bqAs3gQ@O+dQ*O5*wSHA1r*7=^ph_pbNF{p?qU_tl?*uAp#%BcD!FnHVX3}8G?Nkpla@e>#?&oJg$`H~'
    '%%u${Q~}9vprumiwSx%dL=CbtTP4ti<Q^?S9%0_s@S>LBk3yJM0nt`%J5uq4Lu3=<Re%Ua5LZRuB%@onF4n~N;AK?Wp!_-E7p!w>'
    'UR#pDNR`uksS={ACM%BO#^DNJ6i+*<=cgE!it`DzDmzQ$(t=yK6N^_0Q=y&Iwq~c8urSJ6rdCcdloK`NYTQ=2Z6UcwOHde1Gw>2I'
    'mR~Gj^H`on1+_l*VT+2Va#9iaBUvZG`nAO}SC-1rm8?ZFzq=g4Bw_IRX_Q)A<XBGJuwbaSD&TjLeY8AbWd^k9m9t?>2cC$YNR)Pw'
    'M1QIQrmWbo1D;nIk2U5EHa<QH$^?khmQib0&xn<iH^`K(2TXJ?;fKpqTS3IisfMLeeZ)JQlxnK6NWE+kps1>}cQCJbtzAUks?8}z'
    '3iB64ta9~qLpgaP;i+|z?j-zZkpkJE$@yBC(!1b|R3GG$4|2&<BA2kEP(ljpI!f+z7@Ep)*h9-(Lc4KUo($pTt{FCkxGW+?b{xA|'
    'LySs*S&jr#sXo9gA7GXj0cK&x0if)x7Sab+M6ClQ9SFL#Z!>iReCFwZZ0?xWM~5txQcDeQmZmzAS3eBh4<4~`gH%|dh+1sMLYwi<'
    'O{OknO)Q3<u)7ioFf=<TpMqE~K{8X4uerGEb`6Fsfwpm*SlR{wqJ2=jiir2k8F?S|O#%tV$W;{Ua`G;MBzh}Lu#50xmz0rgW)s^2'
    'Ytji2v8e(M(AV&Xu#ScWG^r$9&L?RCpUKqvn10qqI?;G$y{DBzZEnmdGF6mK!GR)m7d+x(>IUKYO_A=S`)H9W%E67VfdnmOjj70q'
    'HaW%&X#!p;TvNv@74awFS*ULio=L6PN_xGVs9|o{2AL@%_h<<Mv07y)#OWUA($*cF<SQYjO(Ym}i)aSxnRuml_KXb@_00&W^49Lj'
    '7H2t4g8==O01K%-T7W>Sv1|oJdI<`dnw(bU(?T-a_=triD^3*L&ln-%HhdGpDNfZ`NwWf!33_xndHri3bJ45rB>ZrZS}eQaD`@Xa'
    '(B*WJaE1UbnJ60!T5<P5I+%?-YnX@)^Ma#i>`tq1mI!c@t6=Zt)Q!T_jfrw6-A9WQsOFR<r<Li>mB5d`{Pp`Ezy0fPKVv_L!UyYb'
    'L;`Qqz=ZDF6G|S7Z7B9UTBgT)DH$y<%8UAb|MjPRrF`+(iln<2qARv?Z9hj-NdJ{j*Xh1)zKER522U4}o%TK?H`!95xhY*lrg@dE'
    'Mdbb0@<@PWlY-p$fg917tPmp2Rt#tsD{v#PhGr27l~m13as_rouMrxXx$5VUq+Gy_S%D>aDNR*;UQt)jNM2G=l}Ssp-U*c?5~xLz'
    'yP~su=Gk66$q0NX0S11ZRmBz5ky|A6FjX|UOJSSfBd>BIH_~UbmBc%NkF*4)%~9jit9yWt%$DFR2c&CvS}dFy--(Tm1#jK)K<E&0'
    '1h~d}VaS+DE;1@_ZzEH1`nasDgM};0I<C@+<zkF$`Sk)oDQLn91|k+r*bvL^1(cGNcNFgFT~&gi4lJ8E5`g4LV3bublbt<PR?m9x'
    'D+6F*M;X8_9oV^5FAglZI3J(|4b>81#cWu+0?_hAVXan@Q}M0<EG>Z<_;CpU%L|2jTEW_CF96F+(Wj}JfQHH4b>IaMC51KD1%Yv4'
    'RdUIlP5@xp6Dr<2^Z{|FM~6q!Hl#|D$2*Hr*?~o$t5MX>f=GE_LF9pGDN7N@eP>i{h@@(zd(BcS78)ieFLkFl{h=TVAMscmB8|Y6'
    '68v9m;$lxhI052}w8G5os#TTO%rI8m+<m;i_S-*TF#ATKlj@s|QGkSVHq4A+$Mdo3Nw4<sDHrl^5>>AsCZ~JFf9zgvOSZ}mm8V5d'
    'OSL>~QoQGz&VgS#qs7C4!W)T2Br3T2gpwKk4I&8x>|7~&Dko}?WJCCR%}gP=M@tZhwRRqjaRsR7bwVvFBo#~8=&z5|6A5H&8eKdR'
    'sYgCE+Cqld=LhPM4+uo4P&k;CMlwrXQP>16p~)a1SY5|LP{%a*EzcTJH_o2nuC)|2M{&s-$dr>cY>97zKok;uxWm>GLXDLo)urM~'
    '#wH@n%8aqCPAmnLLSe&CsSG`3#$}+FCV?i&t5nO08U(mmW?V?_(E<cw!C&j8k|^A51y53G^vKc8(#yQl5uw^Vv-GqhwTfTZUNaGd'
    '#<x>&faMVegi`vNSg$H6HC3MX-@C>K{9bco5CWqiieo5aWF7xr83^%!Ip8Uq_WMTQ_o6Y3vgPmF@$#VA1%v}XFaEvj1W7>%h!?<Y'
    'Q&;#GI935(n!~`Uw;D?we2rrYgxj9pptOfD3=6S>u<+NkFKkh@G7PSwvP<LjoRYfr=Z)aRc&)35%+mu+m<z{I9&str%cP?SKaXka'
    '=NV~+DbdV*t_*FA<e`5bJWV$@!MJoL^7tp9(wvOmiE-Yd$l|4NKiS@)e@}O*;`rM4ZaPvk2~GU{&J#3<M$zS3x<-@!+!#0k9%t32'
    'j!jUd=>(E}zYv4<I?-!VuQ$Dp^_o%kLM_X6Xwb;+_o0}o`@Pr3UWex-GPonwf|T^%i;FeK=Xulqj?kd3wzS&=SP$KO&&R(T-F^<;'
    '^%3+4|9&)12n*rGN1Z5{xrB~HV&ps4^6}VZRym%39<-2=N4{A4{N4r`nX7z%!<We3OJDxxC!4h)O?=sKRqE4vZ5#Wvi{<Pc(8vcC'
    'yg$QBt!z3y(>S+YcU{+TN~sy=S9_mToO=BC-@pI*uRnhN_4`jhe*g9Rjt3j~ub6pq9y1iCANvus1KKkVSOaCJgOWLN4<~;6@yDP4'
    '^3N_I@%wLAj3rr)UCD|g1|lV$k&R%Qsi1{2N@~U+P)2N5_#9MIq|CZZ=jY<E#J1sORBOYoo23u6vgODv)wBKic8&|@r1N*rT+>dj'
    'NR5t5FcuyD@Xwvh*E>0og|c(g2EHH9`m5Ys>UORZgAshi*mi5i)a=Sf!!Vh==7p|j(+y)%n#q;!0!vW&Y;qPI)WxQULY2cSg(l!>'
    'JaeGi6^&$`(K{K4vzCdpiSVSmKsk9swlZwtX6_{X=nM*wEx42`Ad5?gfoyVYQrJ|c3Kl&vQ`pqLYCI!W3Wv=Y!YK!R^*5zBlX?|n'
    'v7EXg;<j5N-AVV+A_c02vMX85rDPp*InA!lTGThD!7EKeb-c2%@|3Km7R(r_R<fGqL=Agu^=6OyGIEa=ASN3`iVd0!{YgPGKhTyR'
    'Xv+_@B{?11G91P6!m}dofm_lBkB@T*w-%hELHy%afVTX=QSKYp2aa+djUPD5UA#XALh`C}JMQ%26?CG8u48k}#=U%6A)wO*g7Yl`'
    'mTt7b+5+NjbHW0_e4`LFQ?dchRZ7$)VYabAC?xmT1wteimN_YsQ)57a1Cmovut@c=1hw8E)RZKqt_%=6$yC_BWdQAKCTP4;34zTd'
    '7;6Fy;{*x9QXSUFIVu;Db%AgyC#!$ijgAP#1RpI!%uFyYR-j0ia5dp`j<6=uE?~Siy2YWZC0^OM+ToS=m!TGhF}n&uT29uG+ZS7X'
    'zzPXIT!vZ_mUVJVYXFxD+ql{)*{)>U0I!1kV40n$B{`u6(0mhI=1rio3czxr%1gEj$vs+vK&;@xtjvW=E}l;?9c6}7>Ff4N3xA1~'
    '?bJDY%3LUf;v_9=6m?RWs<e&*tgWv&2+;DFpyX5RM%L~5bmD8k#A0gG%iuxu#OZ)n_FbNW7H1rli8Kn%SEl=NxeY}(n^>HM5<Of='
    'fmWUGOhk!ZqRe864o;QLZK#ghWnL-kJ5Vn*6)PvcmJaUlNe-XV)X6H$=6m!y&N1gXR<ye_CQ6B06I868aVjTk_&42hvxNj7Ekhtz'
    '@(g-3ZEL&Ko0V4+IAEK)q)G$X6*eU_-fD>7>Y!bHK~*I&1$6hew&t56K%`QuZEefR9Cq66mYrV7fTLv$<ZB^TVAz*H#ktREuSkk6'
    'YZ*iX5#l^libBW;E*?X4!l*fAwgL5pv8>~;my<Wtw2&=$*`0(RE>a~K%K(EDs|}LGX{TYds%wbas8#4rcs&V@Wa@b>Yk_keb*hF{'
    'SEYT8lgr&j2?i;c&5yW<#7fJ_8e#{z<#`JUK3ar8t~5fgfIcrl81u<dT0zoOK|@14*MRj30Wq?zb|*mT15rXLCgdvGb2(X~QreAF'
    'K_S71%TRz*SzDtl#ie3$hSs^%48d!$wxUG`5j?lVu~XJ4z&gUG2ZKied^u6WhQ8Y}!a{Nn7ogSPN7Y`$V3Hl2T`B)R<$$dHhW)s;'
    'o+o4l8Tcs)p-DY!5%BM;z#2vR7)#3s-wFA*CD6{Jbgm%(KBXdZCEpd;H_`_VdzQWxT;JECPsw=!uHgQvH3I!O6nO#yC6n`@4=aGb'
    'FD1bxjPy6a`;GL$uah&PW_LAV0T@|feN+KFMqxFfD5y(p4ukAC3^BN{(y9csO_U(uj=?XlLck^Y9k;M_?^*@cDz(-NI&JXe?VSK{'
    'cNVa$qMYn30u!qRWzB);D+hw>?kt8`ho?IdsQ20W%79M8+RAb^-*#mgEcTX}h(2aU(uQjGwxF_+K&I5YV#-GPc-CIN1XT8gf?jP9'
    'RwbWb)b4W=$AQWgL^>}FDqC=;#OW<}fEd}x!#ZWR3S`BS0vXa=CiBPQ)UE~<Z-P_1das?0=+B3mLuInY*uA)t&zI|>0<41X#*chT'
    'LM+WTM!_c~wVRd2-6s!MRR+GTT?2~;CMHFWp~?2Tor_&cu{^R;o{7M;Q-X!+ltZ&EacWYUg5-^BI7`VJq}Ocjb?+nm*gYB~+fZTl'
    'LVxaF7cZVAT)xv|W-#OjQ(_VPldpk)7A~h|&k1c^dxpoQ!m{)<L0)sVR7fT447g{q<tmI6v8;<VHLE-is_|IXb$7$&(#Wi9(4^+9'
    'oUH!UY;L+15`45l1G!qVREDGhCp~PN*HXtF=E_M+sprmv7eivFHD^r<&}x{8`^dDxw$q;D$*mLW2JJUNZQ8IjFF0SSqZX4Yq+q&+'
    'QGLD=aZb>uTSqInvZ2nQPbV~(Sng?M5afgj2xtU`W)(V7bbV<+x!?xJ+H6747K-#}Ek$CrT`jjS7wJHkxwP|}uNk~j*ms~FLWZ>p'
    'v!${rIYk==pEaJM9BE`kstgJ^=9zcaVmz^X{=AkrsflEUuU4AvAn#H&=+*<NorE7PQy^ROOs46<rlr$5a&n5R?iHE!b0=5<T<Mf@'
    '26Ti}OjqngnQ8^gShIS*shqlD5xHTmbT8dUixjAqDl6YkL4uYbZ{%b_VEQy|A4vuo0eAv<bzk8rgF05Z6LLmvuOQ!u5QeZ-kf3tv'
    'hWUohL3WNsx|8lhMH;D=go#ObUq3m<Omh_e#(SgHJS8&Bd!w*4N8Rc9QCQG@NMVdw@E(RV%?<nS=Yg;^$AM9N1wfal1y1=2042?F'
    '_j-1KlIULy2104_hL4js0%GfUlCBXotv#<)Fg8F;HaXwR>Y)ijcVN)Q1~w3}H+ZG6MBM+(0}us^L9K1xnuYL7Vxyd>{xuM{e6qfb'
    '+@k|bAl9lBMteN=p%qKoqUFxh76-kuYO*amlpv%-oX6X}tKM^1YfvUuk891JL6Vb`-rS~5BP647gQb?0frSh<bEq9XYw?W4Nx_V!'
    '8^^Xv$s1hO#sOKnm++%40mv5CtQ}xq%8<)R)}3d^D1l23udMOluLp<Wg1i4_0urUbUX@(kOeiO7kmcqv%0hw<m!X288Md;Su#`WR'
    '%_Q;eQ_8hL{|_WF$6`wz=KTFP6M!gb1u<$Z(Oyo}AgkHc$XJ4f<Q^?SAeQG_Cuu~nG*PN4K$u7)3JZ^kSzOL4ywV3^PKhXtkd!gA'
    '5>f0R>QW%S5m6M9d$a_BSnLt9VuMSnrKX8xl4A8R><xp5O#}CMrD{}liVb30jjU;GW`pHK4G}uo0<tM2_izbHm=L)5@Bh7U!T<S>'
    '|MH_N7<So2+y(wW|HuFPumAfW|2euD{{|jeXl4HU{{x2nyI%'
 )


# Complete immutable UI173 failed-entry raw arrays: 1202 packets and 1493 events.
# The retained fields are the six login_sync inputs plus original receipt SHA,
# failure and completed=False. Classifier admission does not qualify this failure.
UI173_FIXTURE_SHA256 = '3f9949ca60ab042bd56cac35dd6ebf2a799279b4d144c3179b39c70aa77f8e23'
RECORDED_UI173 = (
    'c-ri}YjYe&jyC#NCiL0ENaQ`|8%?!j&QPS5q&%y4V}nuGeHF)+d}Ph+nb_F>evozR%IfOws;)MXv@6G&W?$<m0Et8bNZ@~7rOB_w'
    'PoF*)PrrQmwRrWH|M;_YATO-`?$039g=X$M%Pyqk>N|B|1=sMO-@VGd{QS#L#kV4V^_MdF>DS`BSH(Yz&)<H<um8`h^k3f!{7ZfJ'
    'D*yDg$i990^7++YUX@?J{QQ*t^a(%qs`)s+`tz5(`1<+jmn8dt3jg}&<Y&b2>gwIY+ozkm%h%VpZ=W8n?l+s;r`x;7>o*_qGrtzU'
    '{#yU0GqxymF7d^0pZpiWAa((g+Y2eI;@tl4cYQ$ZW&iQ{=j4}Pio5~z8(rTBFyZx=5#;UW@#*sF>h8ns<I~j-m-m-fkDL3ao9l<i'
    '$*8mvnlrV4D(3-VK=et&mXhXv^KTzE506jxmyes*Pw#(x|8#x(=58V)cLCfA1p`F0$g&)O#5s0Ol6-&p_;|B<dVl$`;@SHT_sFh?'
    '%^X%CE(yZ&C4@N_3@NxcCwbm}xW0MqCHUrMbNhDl^x^$$WL?Y0$;dd<#&NlTK<5L3io37x+)@&~zq$PA=l0#(>)UBK1iP?CfpvWi'
    '!;KD+eETvP$Aialb$5Haxq5thyqkf-a8t=kdx8J{^7SWV#Fx*X8yx+gN~KAdk}&#HmN^;7o>t55=kmkj4_k&$27=r*LiH(Y_)-?v'
    'Q0{IYuWvt~-g?+PJY3)1&Vgh_pthFMW^?P8lg;hb{m1uSlfJuqJ&Qul+OulWF+8~b{cSoX<&-+4y5>^oe)I6*-3FQV?%l&26uMGU'
    'NtS*22dbh^Xu9$31wVcM^;_~eE1r^neEYxn(x)u(*4><+H@r`HzH^hGlW(8?S@dqQe&LL&2T>T-SH-ZD`*%NX?(eUW<BbjY=H~L@'
    'hdES18#Kf-YiU@1d1ur)>G9+B9qOzrT)j6xZf@ovaZ<?zlvr?K!*yRjEhPc2%J(0iYGZH5#5;&ZGsX<>uSx&!KZ;+!J>ma<{nt}o'
    'l*QMtNCupppMHA!<)`Fd#n-3oYk?DS4updf1R*FPqalX_VrqcYCKhUd6^@u39CTk@$TN_`TNUrns<?c+dBA1#^&E<D9oVySrp{P;'
    'byQjXtB;uyQ`fX=;eL3(xw(0IJBK5NDIOSnOEFx2xW8<67&Bm4CS9Ksz!%`CNP#=S*B{XMy}NySef{Rm_0@-)$B#1*Ie@;g;TF@S'
    '@n|4nE}tH+QD$a=Q7RyhbPG2Ki_q}UBDYIvbF;a;zr~64`qD4J@6afj2gl03^(&Ub`Qh&I&Go-G?zpG#Z|=UIgGO+}&xz*h=6d5j'
    'VYr35zq^?~wVW_o@3))h1M>W-=GW!b<Mod<zwYM%lFS8${9?WL{q^nZr}uZ)NT&JZkvi~J!eTUkzq`Nj8{K;(%iIOhDHd#U)Z!(<'
    'd&KVVQ2(J6UCmN}N-!G>6c_Aog*yWn6q&!>-u?ZyUNvVa94+NBD`q~J54V*XJOz&H(*~BJdA!7p(Bs2w(KW&a!3eY1mS`N6UeDk%'
    '{{4r?$Gh8Elrb)x+qhCJ#dLjp{dj$ObNzodPj6~qvk+M&0^PS*8~b$uam?^`*FYR_dtMoSe0p<te}&8V{pJM1IMrXIBtHY55AUC@'
    'KHT5WRW{D*z@@@rv9`HHv;6YvhwIIcn|GVW?3xbAFeZZt2`r{g<@Tz0=8ZqEb2hJM0W$iW!n66e57+N2%6LfgMA<N4vQHghms>cG'
    'v#0?Y0*P4+;LYap@xwjx<>SNS=H1i7BR+kYgD8x^+Qo62>)W>zceZeW`&tl(<YVq;<^A2ft8-~Xt-pLtY*wPX@Bg~Fnkt)!MJdJt'
    'y@psU85R)gtV_@PD$M%u!}XggP(O?`9YMp-y9cN>8k*dG&sLe>v%r`@WcWgfJp$&S{3<21)X%utKY~U|b~x-Z3rk}@)ywlN7)BjP'
    'b(ss}@E+|56x^ek{Za7wvD$Hm*)b3zaI*`yI08P`jI3cuacCaTg>iT%e~ctno=-v!?N*QA&_;!dRxMN~3(Us~kWrFHK^dcTf78LW'
    'TMFgSF8&CZ&}%5qfaJgy{umb5_clwh3`}Do)EoI-X*q($$uOiWC7cD$fo=R@M4ADZgGSVetI*y}{1H6BRKPC1ctY*lsvZNP4{hS-'
    'TP>Hb!>!mHECCX5;P_djX2i@r2t+em?|p_wV?Uzl^G^QjA5DhJ&&e-U%FHice*IKq?J|^^P=I%)+Dv8ZoKOOne<5X)v@D(BN=SrY'
    '+Vo`xf(by&-~H!gC9Rp$(w<LAA9vCpp`vs4Kp6iN^I}i*;xG=}+go!mwP{w?PnSfyc|c8l^~2K-Xz$$Jf1JLWYEU8wU&v*MPK>74'
    'NUVzkh~^+8K@x7AtgwP;zpcRpShNBwNmQamOULwW9nfct@_XxaI#sN7EJ)0!#bQ+~SR5OK_$jeKxWlEzB26@O;Y`MZMMpEIo!}4+'
    '6dezXBy;g#(LvfeDHg?bkgBUFu^1W6G}7Q?G+1;H!Xd?CAf9E~C>sr3Z0Lue#S+mnjk8+Cg2l;r%sS^-B(m!m6Dk@g#_(9M01x6R'
    'i_?z(zPWt-VRCwA4M9so41seO*a!9;SzB$;?-AMZFbhqXA-Xu*rB1o|czfmDQL}(Jc1Cw^0AuGQ@IjA)3uo{0?D)#{eD&c?9ay@V'
    '#~*<PLO&GB&fo?=6^jfk+h;%0QDIOJoKfVKP@gFsB-2?z5G==4PXwp1KrSXp?VWsk?ehof^sJ|MA8sD6-`{NJkVo6l;&%(({!?Kc'
    'p_frY1aVr*RH0Dm0X+W+r5c0?Vtzm($jF*NT!?7lROs)gNP%%a&K9IKEcW!@-9Ej$yM6HI@qN5(21OuD^HcT=(YyHsfkB*H(})Lv'
    '>YH!cEF;Dtt{fwX3H;ck62c+a2oi}%c&3L;LWB&ww1gree#5ZKEQ&a*V!$Dlib97d5HboJQBXqz7g69)=Fr0btO`}Tpq2oULNzK_'
    '?8rD{T##%a$P}t&HVTDml@qb7{h{Ag84^i#zhS_51~E8e!RAtHDpBPuto}i$%y>9yXmlC(MGzyIG8}AhK!{GEad1)WsyOHLTTIRk'
    'bFs`B?!v-=WSa<%yDAmS#1Ua79U?gqzg@P;9AZcw>~{&Zhzxh$q!UMKpqCKE*l(5uG=~@}tk*-RMU)6PSC&vjl+lLVWaS!k40{Q#'
    'gB&r<$wWk};A|GD7SS%S<CP{6kvR4=Mg{Ag1~Li3c^i#{*sy>UjSjJ4u_iJRv4b+PbV|h9012sxI3c5fVznR_SAV!Lh9yt1&?+L6'
    'Rs>>W5fK4lf;N$efC{p&2zkR<G!7$y8(;c;ui#qfSSTXEm?$>C0-2+tp^BFDVIv`;2$BdXgo{H&q>RQA5Hc(`N{U4Vr)7zxRfYM0'
    'Wa6rVS^#ve8ljv!w6%Fw3DIG3NFou@I;@F8IcE&8NaV!CV-1+_lnbfI+CbM6NvxG32FCze0zu;%LTR-QVsQ)zf4-ewMqHRgLM9^)'
    'M-+CNWX#1PBa($@PHALBGNWRMbxHseM+%q(u4C~*O9-8MG$H~)c|SuI9gtiGy+8yoPE;NVv8X^wh*-lT@sZ&F)2H`HVOSh_`BGRN'
    '0X@7bi(}?W9>ZEELq`DNbdf>V6C!db7K!^z4zgIN=n?K@2+3i>qUF*Giqd-kpuxpq3wbO~QtMQIL{Yjpj%|7@E`}uI3Wyc4h=~o0'
    '7!Zkxbvzm|aiOb-$}I9oR3v8>JQf#hIK_EdHl19W7l0$-EV<-z9|rCh(2@E))h6n?xJaM($gnw_;vj-1uXK8jgR~KFhzl9y9)sf4'
    'EaG9YU@{HExia(&5)fFDju~qH2pz`+5<2jUOG#tbaw!7G30<<f$6|xHuv;p$!vf^v0&|Q&E-0gh%Vi9xlvRB@(^(S%C>=HtqR1ro'
    'C~VNef+~j_k>KVvsMEN#eP7%4;Qh_z$Ia`i@Y{4aoSQIQ3)_qS<MYqSFTWId1Lrrnx|LQOslGRh7?pHX^#J>=F`lmO-o3xs%#j$Q'
    '4TF(RBS}_0{QTvgzTe1~&*i7DKZhMhreDAuZoM|Et-^^dyDK0Tgx%kTV?GnEez<&m`fz){d3#;WkgCJg>(@AE-rsNDT>txwqI+N&'
    '(}9SvnF4xVFu=@NNmXmud9wyl1of!qQsl&II&RK?=eL`Ge|&m(d3`e%j}*?Rv$T$x1m>_<NU1@elQ^wb{r>Xt@dl-I)08&-Fh^LW'
    '5*E&>Tx%*-?IvIQu56x4_j7orBwI3-&qNg)BwfmrX3qj5giUM~i^|QLw^d)qr?<EQ%%_Id0KbLgcCfy`xxD(@PUFdAG;)E5f3Bb`'
    'qzPJR@(g0Sj08r5Iwxb^ez?Zz^8MxQ-w+@wx!dd8w@-h+e*EF}{pH`iF}wL#%l0fvS-XT!zX>J_Mx2vywYGVBzj^F9``5b<_qUff'
    'b5J>Ob^)c%1R~(pl1=^MMU#8GGuQ|%^+kCIJxEmnY}~JYxS2lf5EO2QR1_|FF0|DLlX{<H=Zq*^a4L@KJQ^2<X*la%@$!Cid-?RZ'
    'xqSC@f9DZR=8X_c$R$R^qDxEAJQ_Mkqp0Yh!V1B(bWq_A;CTrV7LH!L;=O)T8BTw_yS|-kJs}z`hla~6N-Vs1AdYY*N<4f-mb{zS'
    't`fl*2&`B*jS{C`T)4BEL07)t^y|y}3e)X}cW8^;zD9d(1||rbL(cZ(oCAS&{I}Td++SY5p2;F7tdaZ-`;3#W?Sc@TT1tn<507{E'
    '*E6h9;WRUPfMM3{pK?hbET_J0aAB#xXSi+7&+BEc_ieSy`G@PxkDIEc_~Sipb7##*rzL|0tL7PTNOk@=ga`JBn>3uEkDI5fA2yfM'
    'w<3s1v7vo4i#TV2psYRTeDU3P{2u?|>VC7ieY(ASyngd>4xbQ_STK2(U*8$^8@N>OkuM+aH#1mctQHUl5*H>0!@@{b3t^_`#{)4@'
    '5X3U+VxWg*R?0Xi0tzBQ64olA;|&)!5^42ykD?%nFfI~`gvWx(2qFcKL`D<<kAfu1Mza1|6<PvxB+*vI0mKaY@X-O$G7i(oYR4f8'
    'l32szpon#`AaObll@|6lCBxxZSO=MoGmaS>$NY7mTogj$zzo9+R3za+t{@#ncr@ZFcv$OREba>&Qf2;$1`kR=9DI_4wv}{1lnr~%'
    '$#W#fcX(!}#(PLw$8jzcu_(qOQMyXTVIiP_pyHTAT9TjtM-(P(gG)yaBLb6&>b#am5@drDimDxysUqWz6LIX%ap(xP#gZ|mSPZ6H'
    'g~SCUVT#&N@t~ZJf=%Fpv=tDJ);vH+oZ0Y@A&-Dx;ZbHnX%;fncrggG2)Ah<B)Jet!EF>1Oop-KIJA!n{d3Zi^Gk&pO2A|cWC|Pp'
    'K@6C5Sj`T&A?KYoJdA|12<Q}6sRpje$z)7$<|qzvvS-e!K7C=cK^zp8mz+HZbwULo=!M9M(Ca2SH6&ny%NUkgU^=voOa!#CA*2{='
    'SpXY`wFUX|4;+G+KM06`PFy(|mstyfITeMvMxhzR-y>M`5mZ<MOVM*o#t?5s913?H!NNhlmVpZW%u(n@%|smYONU__FcA>P3}ndA'
    'PcI`?9F7?n*otHm-MT=8Bk<^f<1!8l(OD74^2u44#||Lq=Qqbqvy6j0AdH9viL+5S5;>Ql#0W(_uQ?y68Zz1lTrLCJoJU^XUcQ@M'
    'M$)5ETE~M%3LeG6glhoALlq^@I;}m58pM3Mpc#B97WmAB(OgGD7p*|VBQPfHnnI064{~&3FdvK+5s?VNh)5*anpkv=Q)f*}Tm;1h'
    'CLSpAKo)oUte)%z)DcW*8w(USIN%b2r%yoGLz-6C2pAlliy*QmxCt`FBZw4Lg=!)ZYQe)KBOZZ&P53;cfMw(=QAjb!uyirdNrkau'
    '89}s24C-=$V&u$Ia*(=gW1y1_BiK<$RCuapr*#Se@AM#WBy<d93X`;G7hMx>$TWE{LRiLBB<q`nfhik<_*gSgkwDKf>mr-@PKP0E'
    '^6*WSLLV%*5kQg=X(9<snb<P>BuFWuaVts=vFvB1Z#NZN3cd6tW#dXUltP+Fc570&uv-s(!n%}$L`+%@Bu%J+Vlb+uVn)WJfs|H}'
    'L^h;yR>fs?NG)t6rmNIP%k|F{8s8G*+Bd|iD=UvcIzpYnVFI_<-!P=lN%PBu`OYo|N?B0+V0VLAVl)ZS5h_^|lnDoSmVIJR37s_G'
    'Tv(Df0y;Svc+{hqcVX_0i2#yf%EiSvzsf>vR6?U#MkY)O)plHr<AbBul;)A*%0y$UDG^X60#*rb;z=-5!blqrv!o18q(;E4ux?Bg'
    '%14Pvl2MeBO2tMU4G_`v(qTz$N@i&bk+{v2(Za>I2~u`Yo+%3RUJb$uglu!l#I=@c#$;rGq>Ds3Yi4b1b~BO(BAoadq>IM^t2yIw'
    '89|y4GTft3jG7-V+x^U36B1&X`9epu!_YFK)O#&WnCu>j0+LQeL?k6_JP~oN!SF~XmKL!jooW+y0t6>wP|4ac9Sec1if!kPJ1`!L'
    '{MhiwL=@z4u{bsmi8N7}V1|YH?lB;eVLhTamQur_lWT+&R*j8>QiB2|aai>RERRgkxr}e~W4Mh`q{JZf69=s%i!kNF3{v9aAeE9l'
    'M!C|=MMx~IW26;o&<JT|jEZp*S{~Y*QEa2kp#D=Nv_kV-MJHHxaLzFfT3Mz--((bWh1*YlG>?B4t#-|;IYa^%9tK&Sr+x^`5!!I&'
    'A|g##pUF@X#@E7(h%!=#1>i`9MhO)WX>_Ox6(wc#@qGPfq>Pc_9*&eW2a7vCH)ZUgRyyf)aw<$wu`-6m-1!ze0W1^2VvcKPIK?6%'
    '7KADCR>wdqun^(y!|_2HR15~S<8I)Xh=W!_4Oke1MeV!>jYpdg+hLMwbEhI&=bSP+8ne-95qgfSj$(=pqqo+@FvX0t5$!*m3A^o)'
    '%8}JEdTXmj=<%&<PDSXh1+*>0LMAb+Yluqo2x$e(MdyJ;RAB*C&P)`<;$eu81B-!J+zxa@9Fip@i%_zJi;-5+#kXw%rnHF1-UOyW'
    '#A1mf7%go?v@y)eXlP>&*YbF7+E@r#MM@hR<ec%v3HGnQZzlWqA8!6OgDTufd(MCe;<(?uznPH*1cHTaL`WcnDXkO`e0M!+2!mc<'
    'j7ln{bYZsB^Akg=L2oZ*$*7^j04f17%piG*0)o}VS^_mCIRatHA()^!!Qy&G@9uuwJUw2ciTd!j>-X<BuV*Zy(rV(xOF9;uFLK)}'
    '{p0h`$uGYYd4u6MxO=As^{jLb;G9X}H7P#cUY)X2QA`L+OAv*7xW3VA)LG`o51Y&T$L}|nk8`L2oKaJw*{W@S{-4FqelC<>zW#Ue'
    'H7|1f-hch$Q;sI^k-Pro%dekm;Q#Swi<h{t+E;T|nyc^r3_@LKW}OpCFm8mD-&uAcC6~@{B_x6}->C~LxCY;zR{&$m{pTE7I%>u1'
    '3lT-5coo;2nj9v`Xn0P=i$WF_rzN<3A;=Ms@0pa}vrt1AcoHcf4D$9UAXrDdUsDPcH3CUagF!bT3J8vPuZk9dq*e-Ak`uvDs|3Ty'
    'ZE?dLIRquiAy`JO6o%!$C?E(%Jtr+a5vYCrYLEv-fq>j(bOSd#1q4g&8qkbfCuk<lS>!HsUCqMbf;Ld{bRb6@Mn`af2s7~Hd8!k='
    'zq$OlxqrI7e7Bhsu+=>5-Ep2Qn?9IRax@HwAlYqkjO^_@l$@)-Z62TA;=ilQht2%hHX1sC;m>9|L(YOh@ZfyHnS|$lb9wWwV%Kym'
    '(i$uKk}MWx{?#B(&FjI<F+d>7j4IwQowLM_BgL2@HpLVJVrKy&(2^Q~v(ykcr<O&oft(0~;#>p}gfP^M5Y*v)#Uy9cRFG0zY6yln'
    'w4;2p6lw(2UVVgM$k!;%6!k)_B~VMF4t=Rgo+a@5=JMv|>E`lwM%)phIBH@T0BQub*3u{D6!hs%np2>d6_#4rTS;#ISf{D=oa2Ie'
    'UO5$*KU^+%0gY>z!#Gfq16LGZoMm$L!{y`CU+=DO{a?4Yo14jKlrs<*WP&Yo(4C5c%OJ4J4Jl0o3+w`JX^0|JV5tg8N)*WglTj!d'
    'qR1c}l>;eFRA4!APD2u9f<3-kejxwD``4F`qvh@oK`}<_K`Q_)7k2dBkL1wGZ*Z`n;)Yn>iN0pc)9u~k^_!0~h+?%1B0*~5+7|+;'
    'q-OJa4jyCrQ%E>E%2*zVi{`|Xu`VcYB^Q(C?iLM&+lR-^ePuAr!Q$jOg{CrB>d7=?7C9Db7C}c3=j$_{QC1EiIYty4>=8++0+Ks='
    'F@YfIL2EMB@UVO^<pg#-OjcBugf-j-?gVYfcq2rRBt^;_AvHZ~gb9+0wIE}S3@Ymqkwa=73ps4ypFdNW{px;m`S{^}1`?;3hI6(g'
    'Y9Y*QBY{Bt!LLZVY9Sgi2rg4K+wo9B2jl30?s?X9z@z!O5XKp%!}{IwEHzF#V6%@6A|#OdU;#vmYA^_k^Dv3q(HHzQ-v1=yFuN_Y'
    'xP_-)DiH-YfzOo6ia{ho2C9e7im_lhr#3JVgy2C&Bh|9)k%Z@B7T244{K0FyF_IkOi&F^XQ1ztwKrSC2FR%XQ^9Ao8=irbwtopK0'
    'K=#5o#2192OsHh(7^At9QE*0w&I~HfAY=3a@4@paGsI%U63G<W3{f}%k;tlZye}e#$f@F#V=Qd^Ni}O6Q%cg$8aHThPA4PYxf6vx'
    'b3(+R&zyu{mmvuCnUhA)>ocdq6;JW=NJvwVZ*zjo1{F3GkZCm)&K<1?Wkm}fhw18uu}T`LH6Y{AYX*YpV<nlmny_CnorD-0fugru'
    '*eC?VhJ_G_$l(J2J?XON!t4SP1)>>~K^;NzWe*VrCxOV;J?+cTn;0|+BH=a$KZ$0XIr>?QFqD&Va7GMvIAoj|R<<YNOn6j<&`qM5'
    'RDsz_q+b;Tn;Ws%cz$@lxw)AyA4&xYWMobfL=ptAr9KZq-rmijhGv0rM#dFwEj=-O`g9D$FgDPoG{msnL_v%&AVEV57w+lEXyL+|'
    'f+WNMv`bY4!~mwOBPRxqC>*<pM5`F=FW_M5xBCdgIUWaNgpR`T;OhuQ!5OI`64!(F6{N{6V^BdVG`-^iGz4cF=sXXg<8X2#5Y2QH'
    'li2VG{0?ADnA=Im7&|DZPsSLlxrl%>E-Yb0s$E@>6HTLCISUKc(J3>|RNzLXSM;1|h{H(YAfvEeIf_dJ-b2o%iDO&A2gRDn7$by='
    'K)rHdOeETsORf#QdX*+F<CQBGiSg=@L`E8AO$44B9(Eulaoq4I2w|kP^ptQh_<6YvBW5(Tur}Q0(XG3V#}QBEJ|8fGh1U(5aFcOH'
    'FkxfJG(#YU(Pz+V0RWL?&?1(wNF|L;BzTxfL}q~qG(mJ!CWshTIG{%)!WwUu37S$!2t|g?7p##Km5`jaT*oCgPAV5ya-LH{M3M`x'
    'eJqq->p5+LBjjX>&)T2Sj!ariY=FWH6L5-3={Xy0*Es_coo9gAz`!Kukwx_%td)|HBeKD^*)k%bvDSrc?2IE38tWv8cqTT#U<@e}'
    'n0%7NnyHbPz;!GMc;s<75!%3-m_=Y+Sa8e`aR?l9jMH-nobP`VL4gd!!Y$KUlUB#8P=F46$264-D<nLIXfh(f4FGi-dxb*kAT5?='
    'b6+7*VQ7w&H%f4N)@W-*9IP=)m<UdPAQtC0W{#RSzQ0*;7}Zem#yJ<XIio4m$1gxsxdzmQ`YIqog-IZqwjQ0wgr;Lyrb1ZCdUPI='
    'Wrpb}^eq|(powGu6$-9{EETGva}^d5BoI;Qeh<WOLu^1I3K{lqp{cK2AyLvrGHnbSR5qcQHHJySV~|wC6brKdh7FFNk269tBjM04'
    '{W(~JD69!44H0V)h!bI26`5w05>S^2;#q?zz*tRQ&a*<oLxr}u)%5)ajgyDRr>o7o&7-$cZmu7uyHEVl1QQ%}n%ic2@%4=k!%t+w'
    'sx@<xYhq#5dQdNeN>&jFgcSklSYrXCk<@wwQRra%N5vWsBsld&xA-~$6&$gqSbGtK3F|{pExsN}*knODOXH#UCuoALIX<WG(BoDD'
    'mpv0fRLK`tb3t;I1QLoEE>s*IJ~uc3N1;{`0|exta_=D!&Q%QUe8dF+GDg#~rb2<Ds>rLYS4aed82m+u#iG@$C8?XHLSe&<KN>ep'
    'jl>4tXxdB$MC5Q^5tMGGS#v5RLBx+DO72l`5D>wNBQ6Bmt`4Xb8=|mbX&{<Kr$XXFM>yT0BRCitwi+Z*Y>2{!RrqKU7%C(#3g?8l'
    'P+UnXEHP^kg;qh{0M(j<NQ?|)v6hNA{xEH@*gXFpxB?+rkSDB(G@3`E4{gSuk23}|W1JH&Hi!ZSWg`_0YY+)nTtu<h7_Qkto8(zo'
    '!+q&98NpiPkqq3eWHuUF&tc;eido}Lc&1}8(L56CR7Cq5r_qL1Hk$N)kH|1EJSrL)X2OkzCPxI)#zi6yCNe-)1oc7bc_suzCfC9S'
    'V#Kwhac&?K$%BS&J5Zj-zu{0FG7%G#jCRUIHP?+{kxh0)WL;c<&_0f1=Ym)`0JRB*AWYc2!vT@1F-Ab(nxfi6c_d-kDw0#D9*8wz'
    'qf_z;<P31-B5=DqA7ceh?s)gziIk0pNAiN9iZek8b{Za4NQ7pJm`4>3qoZOG*Fvf&Sj4py2mM9Q#3HV(VllKqmlx95fivLQ{Z<}?'
    'W8wLJ8oyPABn&OmaYjitNPH&X41!Q$xfv?XAQGItF@&$=g^}Q#q;)BJ6dY9GW2MR9tdMXXMp`w{=y->#unisY7ATawci35FBk+JD'
    '7K>`$aAIA8D69!irWr;fuZYA+t0PeJ>H-(OFiY?GRY?T`R~t>98CN5*L7apt5{_7u5=>gsP<Vv`mp=M*@EVCR@%XsZ1vn)f&}YU~'
    'NE8F=y+wt?4G!H3s`-P$qN(#0DilW3TS*m=u-!G?qNBL+>EWaXfk$B>sHaS`x2S+{7RB*>#Nw<{Ks;v<gmz)lBGIHlBqr>UM#mcC'
    'D<f)R)*uM3oQ{Ash(v_DK01Zwz%p&Ad4ni8kHU=hNWvBZi%Y~`zuP=Le7wE#XQZd|MH!)k)pubf+yI6@sy&?~%E+(@*W&&7<%j#r'
    'xh5;ZP&%kbvd~W42jU1Vv{WV{OWr46MARat1{718T!lz!!Q(=tIq1j`Sq^a_GE&O85ZTzKn$<x)1i?7XHXflk7I;bpD2jc&F9yzn'
    'ddhZbZI%AgIjiCuqA`*mL^HQQUx;Nodk}|<OX1+2-a%Y|l-7}vNDCJkqCvYLnwtML5*1WxB}u<RAeOPvxS-9!S3cQD2P%ikwd=E<'
    'IB}T`kHUf$@tExTf`PFjbj=V&I4dkJY(@6``+tuD*KA9F$frUAVIm7ngNh1?<-vZJqCthn;S|I)d$><{wdDG(LV~2B&Rq03P@M#&'
    'e5pdeh(-DNLmT?7Q1CEKTvO>2MB-vNOQ0`s)nO8dH9dmhVQ7;kfxkwA1c|^4uP+4d+qo2^VZ{oC2=gU44QmjHR3IW+bcCypaz!zZ'
    'rDi;=_(U<0rLUImL<AEVk;t%`f#8<LB2bcB6_n&ON>Z2vN(vcfVA1rbKqOjP5j4fKXF&4s`1JPr$7VKvco=C{aRigo^nEiLAi+_?'
    'h3>&gq&bX8F%@LrqB%#~%A*41f{cC;in5c3N2FQU@)s7bP`kXFK_HC;5(gTJpFp5PU=Gv9Fv;TBju=4kB`!={q2M;iDxlhqAQGWP'
    '9QzTYn3P%&+cAhjnc)06l^ugfhV^zFksX7JlJ5>gT{YSRQDJLeDqoK?f(>?yKtd3I>Rd+PIyM(f30!q(OL$f&Y>*{D<2kN?I1Vu!'
    'PBj-?DJ}&yYY>Gn;ptRC!y7~*HSj2SBXHYnI1uwj2nB-0z#BxuA%^}U=0f6{CxEu`T7|;0po|esb=4Y4P$PnlHJai4b((nAAPR0Z'
    'eR_X|M1&4WI*q2KmeM+E-bk%Xc;cQ&qahNlbQG*HMoX(Xu|`7_8tAL5)<CS05o~`=RlL($YK`WLQHCvqY4ROvB!)hoPyyjA@K_sy'
    't)9nWnGMP+(q@*Ks#G7EuhGQiDnt-UO$>;fjHljgg@|iz;-Zn@+(w4Ts>tL>Dizu6R}lDn1k*%og+Cx4_*%GgBsv;*YRp8X5v^gN'
    '%QON+poNMHk#BJm8KSVy8&PI`1x1*k>>x>Iy$52gknvPau@?-t|4!2Pu&j^>rz~;mX@vu=b`ukixQU|AXoW<D#Tkis#4U@9MM8(!'
    'ePkRGT7!##L&6tjkHF7rFMt_lh|8)~C^!%M@sRjgYb4=zj>?&5FSx|5CF8`rK@@^pOYUc_kVxj@X@6rcB(sVKnQBz34UuT6s88Q{'
    '91gUILbXZZ_tb)T`XCDHf}?I!stu9&!}9$-houo#1gKdMy5WjKSn*|}xQ#+uQPp$DHL<jMUnZA40%=7gDvHxO_QEk{9iwgh?NI>Z'
    '!4{Avs#YNxwq24mio|IUVV;kYf<luxt(1}~0z<$V?@UqTh5+KQ!bFg`h)^t7AxTK)ujN{Y?O++v{I%X^5<?1>yQtFjiJOjAD6Dqm'
    't6l}f2`Qpr4F{o^1!C493Y<130^V>hsy2>k!_jPIR#5XsaWofo47^c-i6|NsAQmf_mbB(#g#w(VHy0};JO)F+T}a1qv2nz+22nUh'
    'U;Cy8;<$`Lp()@tbWTuA8bsl2=!e!cyz$xkQpTasj2<j|1e`$(&gdA_nbDGI5l@9A=ezVs9n@^1ZJ%8sQiHY$^fb~kqQt=pkqMok'
    'F(A^)#)ZgoCZj^6q==}Wc7;eW2phwbq!QIo0{P*_JiqVB<M3g*s07(b9hcNN)IO3&hA5(*Srs4~mYgMOgYKay4T1cS<mh=I+DcB|'
    '>RYl4#$;d)5_q{Q6uyW<EJEu6fiy~+7#IZ73QJrqv%;Y`w<abY3B_cX>QBWZe=3}FdL9WS2Ypwmc_bBt%_NE3Rt*+oNsp=5D7fV^'
    '2C0=wsGz(ONhGa7qM4<iKT?_Sz^x(^R^zjKC|#^I2o*TbmX^{!SwL_x4tF9%Zal;SxKA{Om@^21hk+}SY|;ja5he=OaHa?KYA7^3'
    'qEL>DSSX@(a4Lz!-`gNDTG8_+EJsF24l5%v)Fde2GKLKgBH>yXa$^8-Xd7md3aV+WnKp*n8bA<^(Wj6!NQ{hQS7Fc?5R#fVh{C$C'
    '>j}{C29Y@9WE88PF_wpIrAc^WtmNQgp@<B;!&GJ?0`YZh=~<&iQ0Iw|9@+$j+9*0GBM?_BSMm<ZH540WqtR6Mt)aN^P%=ej-wKG5'
    'Ve=%iKAj$oVZ$<5&)=uB#=)hE-~^I{3uf8iRMzurwhDy_O-34HtwIt*Mkyiz!?_Kcr<&*I45C1Dz>x1jYb0TlIy&A6+<i)+h<Sr3'
    'lnq=rRJ=hXT1yiLZ#c-X-3keBI4BhbYdB~wL==mSQQ(+%#EXqloP}9|REv%AMX`f}KSY&EJr={625Q#eniuY~Na};uNCaa%j%i~7'
    'fE#MwSl~QpH$XOR5J?aj2QU;HE%1jb9Sc14K#-zU0g(U^<+~sv2X0`#k|W|Qbdi%*lBp4SD?ct8`L-gFA#!mEHkwm`%b4`wMU6;;'
    'jEqJ>O-GvK^csi?5}vtsB>EY5t}LE1-;!T2CYXvSs9PZ#migB7h;*3!M$a`af>K*taEhr_K@lvN<na9UoGKhrhsQU`1sQn~L#l6u'
    'M1(EED6$hO9EL^3A}NH{G6oh&AqR&VXjmkLG4Y&M@`#j>;pty89w{j;D0&_#>8yw$HqS3m!#M+_bxJD~{)m($4~bVu2CgeY-e|No'
    'X(LA!2(AqI;r$wk1jeIajqn{r84yn!L?OerR8-Rjksy=^dfj>~TKTig)V$Hkg$)^LlH)uQ&7_SXPXV!5>5L|yH&!tN^r52)3DB3G'
    'L?DuB2*QgLXL2hTDykiZPYh=e1B1Z#d8glCAda947u9JsM50l#(e^a2QJAns8qImN3W;S#M`0gnu3ea;M`62aZkP)5(THqUL;@n*'
    'dRjxHNE}*6F6=kYNIZT{a{)1^R;R1FVC0LRZz2j@L}92oeA5vplzJ4F2@`>xhCqPp7&7C;g=W5`B5fW?g~CZm-de^Z0mi~I)P%h8'
    'hj2Nq&!$2l41Kb11w;xL!*NE$VtvIF>RDr1u-&84XB7?=PaRAtFBoG^#M273LIg~**buqM07cZ$y9UI$jSZ2DC_ke@BxGb#Bw27^'
    'Rxpxeh#HCtB6ETw8$woD8CuwwxP-b#heyseH6ma<Ec3<b5jo&-Ap#Yw88p4BYbcy6>N=Pe5H5Le>WelV3=s*x@23v~cqAw=g4z{Q'
    ';ZV**wQMTjM%oy7q;LT@)U|3V9L6{m6OS}Q(<TZY`DmJ@XOTwxJgkdiY4+cU#V{FUlPmq)`|k>b3c}BtBq(12(L%*guMM#{(2TZ6'
    'W`n|6`e03k#2A1Gl3C;hFr*4`1-lA`g`hGhP1V*KiHo7P4r1Yg8*OM~Bozwl480@1LV^=mMX}llE@YTzM6lZULmn(_`%ARkcqH0J'
    'F>8e3Rwz!a(GZ2xPDZfW2qTyb%7IZkR-_MMg~c!pjTwzdgwW(>G{UeDMFyq3&`NPGiPsziAqKtn49)D(zF4@Uuhu3noKhyNu}@O1'
    '%>!}D#?T_#V{wW(sffiDQ4Cy<RN{(A1PhO65%ES{`1(qg(dJK9C?u!vL);(<>yeOn%GCw;)qO<_UK@2GEbfFYsU2N`@W+tI?dS@L'
    'h~ng)x<FaA#3v~#5Y9RJgL@u{WjaV$#C<W%{8f_iuo|^d^7$=+3WyEMRV=RCS{2iMdVBq2v$^>2;9t7`I0F+ZH>b{5y>$|z!|XCB'
    '#XL4DIj(qARI&^L|2-^@_UwY10mpftMjy_?h3N>G!`wnMH?U!-X`^&dU4)i4S{faN#cRMBC5e|z1mT$A5g5E4i8E0cGsZFwmNsv?'
    'LLs!E4?$H(qzX<C)6E(ynbw>WPa8yG2H`=XX@f}6*5uS(6I9hTA?(*j)HR`kVoXrGj;=!hqA>;)y(aDu;Bi>rfGnB}8GXSRXAzyR'
    't^fgxC}X=u6j3|d3J{k%p7M1SBEcf#nb20ng-CK0*-Vo*>=#W_Z@Ge^WMBddXP)0d;(;jNa4#k<0cXy|1qig&aUsH?B12>YpB7P;'
    'eFa6RuxKwumc0ie92Ze3Kmptc`ho)$5}}zR&TFV}7!#NArML_W0Fm)XaiyH5=aJ&hxu~?A2I*`JEYi4mb4$-64Nj^U3KQxJV7L-l'
    'S|6uJA(#w~bkc+cD<u9zQ$*9pZwoXx5zHS%g7b%d8A2R`f<%I9`Y4bfl_Q=$h=N;1U!Sl-A`WL>JRff~m;UTJF>kbQ(h;QV()6~f'
    'kZ=*!zoW^0)E7=^{Es~MQCEIw7M#GQQm#&G=Q!~}S`Wj>aBE6+mdRWI7;u_4;jls>c+k;`rZ8`f#Mv0m03sF?6iXZ%uTVG$iZs#K'
    'jWv=m+(<WXxbyk;)V$$dqcIi1yx~>B#vm1mWZg4Wf?e3skrR}Qsc;}o=nF_#U&l*?o#!aly$Xj3&xz9R`|L$sPK-x}$VAkXuR^3^'
    '3Yb@jbXb}t21F*FXmAC{#N_F(5jh)~7+DjjMWPyK6%;1}`&TeSqN0IYD<LK>agZjW_Kp=IH8{skPb1~Hiwlu2!A~E3t)Q4N3@k`y'
    '78hIxr?%MAY`llfy-)tG65;ONym{C>j^+p+CXNtc;Ar74W*5^OERwSrveK=u{-&g%J;_y}&@zHr>lG3M5mfQARTVl#zm*YSV`{sJ'
    'h$I@tL6#C3ha}1hP=~NQj;KmABOv9RuqFl;Y39_yN@vf+A`K`k@${ueL<SfOQ%npIkBr}+(6h++;`C80$^r@Ef+Kwti?RUUZXP07'
    'lzkROSOSMipGe>lMAkeG-&H;)CxaB+avp=ump;O#Ik`fS0!b1>AxC?mBsT^uu|h!<E(}=E1aUkP!B}vLP5_Zd451hi=r*&o%E@Ws'
    's-y%JHlJpeiYAhW8GLj!8C02Ge6sNU_3hiqgfKox5}v+VMuzuy^RBL3V6-kg$vF4kb$Iq;@k!U2cke?BQP_jHuyRJ6S6iVFTB```'
    'K|~@^Y5wnje)p<OKK)eWPk61b|9blM|0Y~%{IV7WPje<!f`&k9vJ|)~jm~qS1kVyyN|A^HmqcN*#1)Jurm$I=mc9`bcgd^zhyU@_'
    'L%sjUXOCd>_3M|ffBDl-U;gXU=Rf^geEarO@iSibPe1?T*KdDHi$8t&jQ_sk%@+BezWw)?KmS@}Uq0u5`t<qJw@=AWfBNNXQGWXW'
    '@Q1&C`EMlMe;^UR<p08-e|1Qs^k+}w@_f2SroDc8|Kt0o>)SVX(}ak-3*c5Zb){!s`0a=5o7YcQKV072Y;NDSax>2bivT#&Ry6^R'
    '8UcgEp9%Jbf>^>_Ddl8L?{6+YqS)Nry}iDjhCr|j9|coQ6ud^j856JeE49T}bY6k#{yjTqSUV=)ZB;F&DTFee>HhlKr$pG^^;PlA'
    '*N3*0P<?$N+4EkXw<Ql-ne(ssljzPdSHS>$?4feZ7Dlw68jPJ+UL9H#f`GyM&CSiz+d0?`vq}%K&%g5Jhx^M}+qvrEmKhsd-0n=3'
    '{g<rP7aym&yn4LGKmGIj85ei$3EleI(#nLTnNDS4naYGpK_sYDdOVv)lJBo?QH9=J-#*SKjFYBu%r}JLWmzbu=Ewq4=KcNMo9nCV'
    '&F$64ITu&T1>!7aIad%*zqke+&Ls(qWvVxKGA`P`b*4&`*lOUK+l@qRKa-}Ab#J6fw}0Y_?b^R(-ut`Q{@u-A|9QTZg#tyT!vM;*'
    '7_<i4zK$H+ViwThLFt0-b*Vb7pl#7zOPk*B=<V-t*n%*6dyh`^en)KY*CfKU*tlZ(_V?57yMRB`ex}eO+tOis?`2+;-L>-4Zh5i&'
    'J2O2MRv>+v-!x{6UyCiRwp3s&&y4Buv7>F4v1Cin?fv4be9Kbk?!DN4f@$94yV?E@{<Wolw$;j++kO`k<$4%;H<oqZ)#>)-tgqX%'
    'EjH!0d}MZe-6G?zd&YT(DC_^G?)_~~T@f~@g#LDW_xIa+ad?<D6?Na1JMG#ZZf`c1_orOlFr!8;UoEEn;n;*R8T8{N8laC4b4>te'
    '20C*c>sT;aMcH3mPWqkRqS7Dz#qYNmFa7sl{+O)snyt3CqVH~>zW?y}cy~KXQQNk@Rj2wO+{ehVy$v7N=EHZl-`%eAz2EEB=AJkd'
    'WAk9zUjWno>Oq+L*Vs$)9KSb4HDHJS>fQPFT|4a?J$t4Yq0rcO`JvZFxzN3|wH&v$+!!i#_<j$*yOpb{=nsFccSrO2aS%&jOYRJ7'
    'M`i_^``7lny}$S&9!-_lQE8gEwDmq_4{{ZD<wf#o{5ZCf?#jy%r0ZD6I@Ylopob06>)Y$c>&u(#|Fd~|Q(K|)%uf?opJt$lVZVZ&'
    'jPUC2_7Rai-CR$NMb*%pXwsT{P65A;*sYt&rsGS79c=py53M$<>-XolWIw!ry83W`KhGoU=_%wAKhWmiK3u<lx4C_++`{u{Xc+9F'
    'VQmlr_rab%rF^?VH82>eXFcy>ZI(38x#@pal%18pLy6%we5|gnCSP6cxw@Tp^>%;L?Q{Iq&E%__@v9r2@ssb}4XzIU>K0$&ZqL0+'
    'NT*zF`-oS8$@d6*?$H!t%2kC4AMtglBFC!xykpWfK1bQSB$+J>o}iU!K&C!`l!;PF>#uJBGKV}Wj7yoxMEi|4`iC2+QaagerX)*?'
    'M5f91d3z<EHNJA~?@0?&GLaPcU8r5#-urArJN?Ar`CI=;*=zu^j*k0=Wo0v1IsOS(rc9(LgZcRLqo%j>z10ulu)#j8%v|@&obPVE'
    'OWPt%2RnnlQ>l^_sH6khs7U)**apo|Vh1}kR1ei9a#pWP?IXfUGb4(6n<Yxo%3vEaafk?~3&^B^TtaxSqU=A`Q!m_`fF3*_>{-TN'
    '2Y@z8(hw%Y!BM<CcXcV*;JVQ2l~ymb`edkUhuUwbkA@m!IG0^R;VPLU^<fzNmsfEnCUiY#Rq10s_zz##__sfNfU}HwjpX;n7JtMh'
    ')r!k3e&6EfY~f>Y_)qzR3iz+e62X7?JANW2_<Dk$Pw?|eUXvxo&!u?16n`&G>e!@@Jr?+#LUo!0*9KoA7XRT2FLPvx^sT*7#PDxd'
    ';6IeE6hD{aYoMwq5KmC!WXSsxxnH7&C=LEgsyqR&^#l?^AV7iq7J!UEdI(>t9KS1ssy<UwYR^BU8|+v`Fp%T^b2aigwdZvheCE(~'
    ')Zu>}&i-}!*Ht6W*`D9thx6F?`x><;&q<?3{G*>2uH1cuB6Q2yftyY=^HXb|e<;eik7IhE|JZ5d<~nUC8q`2Pn9#G-Ss9HUXy+ww'
    'pQrovkbj)(be@y6E8xQ4hu$>@i_Yf*mE@F6b!+^NvnEwpwVIR}zNa&t=2@O(visaNHOB~46M49-`d@FAQ|cqYd`pbX)M|6br1Osw'
    ')sps&kt*TC*N{1g7tArdAj;ICk&CJoSA|T;(xhl=D3#l?<Z=Wrm~p&W;?>0#mndqrJcieBo#(ol2z|Wv7~TSG>Qk!=)U!rqikC&2'
    'i%gkRB5S1>!E49y>IBWj9$u3`z7MbFMP{sT_d3Aqj^Qn3QL0=rnOdF{naZ`|f+Kyiz4UeCc+vdhQ|X(d`cG5T6moz!IfmDpyDAfT'
    'hO~9~FDuJ5_m3jiI+uI|Z!(V8q}=uK<_F|AWy+-*OrtzIyi6U#s|sPg%2F}|$uo@>Lg90-vbyWX2;ROj?&B?NlJ@7@A-qob)iX_p'
    '^9^VG5xlv{g+QY{cYZOKilcZsE`>@;UZ_#LdK@o9ai5BpLu#GRn;hajsvnT+R-pO<14fmZE)!G_a8RG^(GSvYQ*w^!v(n|M^vAY`'
    'c#q02k|a;i=E_W>wbu_QhQPB!c=yO}YSHxS(HHc7{ZIgxCeP{xv5z-Bir1Ffo9ac5cZ>3X7lE{pLg%T=?5I4Xd+@pt?;(9=AxQ+2'
    'dS|_WV|X=}ncsdY?`48an+$Zy56J_-K6$`x&P4i_iO||{y`#^L>W54xGA~70p!Vhlby`-i4A+Z-+Y;BkvGrn)ekd(hll7TITgrOV'
    'd4Tt*en6d@Ck5&UV{%-Rk)s7#^oZMnFOxoocaMH3-E_P-wLN`z@Uo-w!1KKHP6&}n4Jf|?6*0~np-d@dF@~4zkq2F-Fjb!!Wpi6('
    'MPD9%d*cvB6V_VCOzVbe9X74IWiqZRFaPPs&HeS8k57NUyT5ro2OM`=o`7zTyS0A~=6o1Mn2y~#Ou91^6G6<+2CuHJlvc|#viE^H'
    'H6OczrsbX>gC`Bt$4kZ>m?s2E_TfJv2vI|aK2h5|a>gfK_Ow*)>dJ<jAj7_O8_D1P(w6lF*)locM4M3FCX=^`<ZTjpn?T+rk2i_q'
    'ZQfa%Fy1DMw~69yl6adS-sbPMiQ#Qhc$*O3CWE($;BCHMn*iP>f47O>ZPIs}@ZBbRw~5|ul6RZn-6nUpiQR2dcbm}NCUdum+-(wf'
    'o50;BZ@2k~t%cYoY`4kUZK8IUq}?QFx5?S93%*OrZWFSb)aN!4JL?<}bpm#meBC5ow@KHnz1SvOcZt?b*sM#iZj!6p#OgMwx=pB_'
    'EQzP3QP;Al_3`l8!7HDXL|t9m0ZhrEuC?ij8I=?7q*>ML1nVdK`*PNeXuGCYuVWqSh+y>3G4+>uGCX_I{P&HQo<6_gU&lJuv5r&6'
    'Jfr=j!$IC|*GvS-gC-qBhs+?*-V0LqU70G|{hZ2oUlZx>_69$<vouS+`(0Bf`vlj`n`6oSM44RgelBsH!*u((CQYrc>Sdcq&`S`2'
    'ks=VX{hglg7<lu!-fLaNruSOs>+ikRCLHvA{nGBf#><h<somGQWAr^DD6#t*ZzCT4*UZRkdiOP%kI<!|RiE~}7`bl4%l>O3*}aBH'
    'M_zLyuN5QsMiTDy2rpC7c=>zpq)nu_FPMqheJyV=2d}wZIVeVGl{YDK{rGwt@$LVfNk(34Bg4IGm~{8|OxAp^C(lWHZ~Y|AeD@mo'
    '9T>h=7Q@4X-dDBzIa}<~)Rw!LU9$UHUX0Mbp;bQ*C~1=XdSwKBLfGzi^WAGCdiVFT5&kA4Sh8d{)iEEDmwbe#Mf+M$PD`=-xl)e2'
    'W_D>>rONE`ZRa&eMqbOhEZMF6+2*w#t#~@}xor3M1dP0<MqbNzuOZs3Eg9(Io$pG%`&z1Y<vwlGQTwmikrdSiOYd+VlWq2J7OY3R'
    'SVm~7*vM-mbWtPsq4M49s$%4|a+e=k?$T6`U^Z-*&IWd0vwY+=G4h(+y@np)uWn@$0v)lNJyY(!rpw)H*j8TpvCVYk_eN;o*e({='
    '@~B5=*W7O}qUDoOcWCcMWZaEi*X`nS$u6y2L%+U`NJr>A(L_A`_)cXY0=Ge#577~O$7n;w2YJIhWJK_Jf4{>sGt<LP^H0ju_u@`>'
    '^xxcFz7CJd%(*g(lG<}h#^RzNlg27WJ<Yw?Wkc$M?PUgoPc8^^wA<hEIq_XZy<TlSwrh8<gKX@a*Ez>;n$eeQnNkyF%C0i?Qpe5-'
    'v@^=-s7#q@GSxrBw#wA1r^e)=lPNb*PxVeJ{^l~Z%3}O-IwB99Ou<AwWeTzCsh2r+&IX@DPmRb!D^raW7+(cIvJtr$Zu6QX-l@r?'
    'N2HzYo<VNUGVgo8J<HskejZABZ)b0Lz2$9R-|l(qG(DeIUvEmAt#MYn&4sKV)9qvZJEneKHs4R0Ew$+3%yNI0RTSg9$91e@{#c7N'
    '(*FKBe&54EleX=(yJEU5_teVqhb^<giamTDizNkZO^KJrjlv$Q1oC@vbew2=pUTmLRUNluUoDY+HAT9a0b`cf;Tj|JZ{c`Ng5mXd'
    '$hXI~-dArC^vuuCe0?2b^y$@z**DUeR>DY)nK5}?$2!)rj&-bK9qU-fI@Ym{b^QLvF!$)3`2wemJvjyoHrb3ZSfjn`SjR$5u~#!l'
    'tHE$xXk`TcPa325`<8lnvR!uL!TH<etDRLVY%`X+Jd<_&VTK#T6gtoANOj|`GVibgGpnm*?|m;n@LsY1J)sZ0XZF9R%Kh(Y-r<Gz'
    'U-#aDTJZ<waa9F;?|X+T${+Y%cbI479_)dLw>{uFw+FoD_Q0&S2k2sp1G04>>fzLZ_w<4H4p?Og+fTEEA9(Ko&g1~j<N!UB1M?v{'
    'Fdxzb_mCc-OKSGd+w_3EqzB|BJ8<vWf$tRuXkDoN?=jY^$i7=yeeZi*?YC-$JMdn*|2>)Sf6rIh-#Z@;T+ikGd`%W;URNA=uiXD$'
    '3j5#7-Qc|*%|Pu>PUFe`_Y&CuUgq|{SGEVsNBHNv5bXV)Iq=>AoK-i2eM231&-J=)4COP~|2;4V-aC-h00(}Pi~U%5vj07y{vcTt'
    '>sZG+*0GLttYaPPSjRfnv5s}DV;$>Q$2xwqA=%+$E&VR0`^LWRru#;}JLyY)ABx|H3<NRSdaQ@u*Rgl5R~>`*PL4kY9h7?hYp!X3'
    '>sZG+*0GLttYaPPSjRfnv5s}DV;$>Q$2!)rj&-bK9qU-fI@Ym{b*y6@>sZG+*0GLttYaPPSjRfnv5s}DV;$>Q$2!)rj&-bK9qU-f'
    'I@Ym{b)0j+pnAZtNAa-7F$^l^!=M`cu-7ghyw8X4rz;QEv5s}D<Bv36efKK=^tH&oefskG)n8tH`|_0i^r`s#4PXD9{9NEm5APn{'
    'K7Dxq`tot}boc#VH&>7N-mk^4zt-Py#ujDHCBFFWlm7x32U7U|E|_Lk{O@=F^D6z4{|i4`txB9pW+z_u-QACyr-#ks)8*CUHU8<J'
    '-_N)_Fm6V#Z>Qe))!psm{oPGNfLWK;O7^b3d%e%ew@?2pw%5Dz*Sp{R+lS4=BR)QCF7K~?c>3Y`;qmVN<D4rit@~GY&g^0JC<46x'
    '{l}*o#r5r*yE#|ZtbbuuJl}<du)Qk_$)4@Xs()dBQQbAvDuv2{JD~u02~4#$)Hs@NE`we>kEB$k@7I<Tg<wghOKmNfOz<R65+U&m'
    'Mr6|W_42>yztR3GZ)!mK=WUTT%S5Tt`WZ(<Qj}?t`yWi}5_VO&E?~z0RiVrfrQSs;3oZL7d08g5kW2`rSehZxL2x;WGHX!k0ZP39'
    'Wr`?a7iF&Tn!WO4Ng<6u36M6+JS_zdNJmko4N4fGgas%QK-+qRmNIQ<QV*S4ZWDx&;4DFu2`VSfGhvJ<3Lc<L>hHC`+M@K&Pe$pG'
    'miaD991?ns!E(#;G)IM53g<a)O{qD`WtPiqfYLRz%m=j07ofC=G996%%XFWXd6GF#%OXphrzOW3%8}#vRHh+H+n`JbDANTf4WcY|'
    'Q93`Dd)u@!%~GdDiL@*|EmfA4LXXO&X;2mel*Iy+NHOQ8)6%L$d0Ofu&3Kj}?1B$aHs5Q1wL|F^pj0?}M&`KV_+n2kRi>1eOCflr'
    'i7bHfv>cf|s+m25Ii4(;;}TKw>9a>=Qh1a}Qi8~lmWj*<aw!{>e1MWKKq-*pb{D1apX#{-GRur}2&%xpkmJCF72_Ni4ae<(<8}c`'
    'j<g(EArnZ8zE;l+E~MORB9>KaPnjwyMrp|#S`JpoWXTGNzvQxAl!lkQKgUyBpt&W=(i;ItO9POLa#RyRL(6PH%j|TNXa?oHP^flF'
    '&%~}eWCalXZ<vHv-*ip!UT+LL?WI!+g`{MaoFY|~v=YH0{>&NtjBu8F$z>wzzQ=4~MAhrFln%dIU9a%JoO^kejZ;fPcSY4S&eR@_'
    '7AA#ltI+1AZR7qD)jaC%rjb|we0x_F6+E?|%xec(``8xa<Xh`SG?%C@fIn{fkIhHQ_IDFqw>NDcSwq48u)WWZeWrTdb47_f2M@(_'
    'rTYZ8&J~u`Ki}tvHHE3>9U`_m;D>DaQC&(*<%cyoZ@-l_SK8%=M1HV+{7^MNy8CGOk@p%0_W9A><=_!Y76|2#4>{hsVWMb%51P5$'
    'KAuE>DRRZQ9H+m6A^l}4T!M3zE30%F&|h`)L8Dljsq`<M);X^F$LGUd`pcUB-F-Cl_s@6ekN;~M>2?iuTk2)OeAvr}QkFP}Yd&Q7'
    'yWG|KseRnb2Y!GL0`H+n+&CZDj$X25Aw3@w>k`8QKJb<gJS_~UseJG&9k^q9$(RFt5H%mV`)Joud_Kkp-MI1F$F8Ac!w23xFHQGL'
    'Az!lk8|~weFJNswKbpsVeCc*^e1tDt<dE*;OC3n)^CiXAtmaFp2YeANUrNoY{p&QoXteIQIHsQtt{1%KOLrd)HU0B3{nUm(x-baL'
    'n;-px@Y=7-O*7Z_ajaG6WPOD;B4m5{kq`O7O%63ba@6wyKUm8T)B_ImRDR$hDj8eE4`}$24fv4}@dHlfM~-Acn_ca41CSe;9CAY^'
    'S)PF8NPijd0=l`uG;(7qFH&6d(SSU*c9fycVtrn)niszDbDtOeM$jEE@L$n1LT(>HhP*)2wxYQ$_wZ(*vzWy#WwzB>xPVpPZy)#a'
    'MC{HDR*Jkxl09pAkq)^bDu)ct4JCvM<_0Uexsj@JIzMdAaTW2lnD;8}T|>(KYly#xddWzFwcI}+<A-V5+qaJ$+ZsQkRI2)(l=b6w'
    'EwKk}ts!5~M677vK2De`u*07Mb(c(vJ-SQn%$Ag;iA4UCP?nYFv*S<M^2Z_|@4uVIAKc~X!iwVXeBlRlm%oQv?vr5e;h&H3r@c#~'
    'Yr1w#K(cTi9;1I!T3P#o>qll!Uqe_vj}OLf`H&R>AF|HowXy&^l@Eqxg?G#@;6qNshm_UyZyy)&A)Chs+}$>Ou%%RizRFuZ6ot#Y'
    '*L|YCN>ZF<i};Yu-~*h_hoNno@`exm417pW<%2=9Dd0o0wW$inlV{XR>F;1ZB=dYBg?C6Z?+dY|Q-NMeTRv!;<6o2afJuqdr@gyV'
    'd?EfGD10H(*57O&PqAg0Lt9qvv1NB=fy+zq)>Gj(&3)S2j`oQ_Vovr8Cb(T!M{U^y`)`lG;+!1VvU1#(m5qhjK6W-`GY1SXbBYa{'
    'iuxDY$5Z?v%${m1rB;SI$#pu(ds)OY>LmL+u$7F+Q+zVcht%!pBrr)8W8zkU4fvqDdBJeUq2~Ap)gu3(zlS>h(A<Y>;}P3kRG$y1'
    'tCB`%RgdC`f3RqNr+pmqqg3@b+sBjUgPu1Z@&ZIXAAAHV&`(|5!YZBeVzM8qiODaR51MF=hGvb1Gt38tYedRmoDbQKKd@9b@v8)q'
    'Q=2514_&+>b3V#6+5d!cD~`vH4y_YSyrR30cAZEEd)A45S|g^d6FdG{sEwNT@u+`xgdeFESypCyY^JQ((N7sG6DxU!)>Z;6+wvpr'
    '=0%?7j@A09!X*#yA(V4gFNq)dd#JwM-bc$1d_FcW_W1)jJ8UzFdX$|{L%6KoO1kXS`H&;_obRK5E_VE}F3(Wfk^UU*sy_YmUOY9&'
    'HGE6|BYQZG3KrVC+DrcfKBv5)e|I0P&C2J|znujMuf2lCbq5PZ`GGg9)1ntg%4@G-`*;dJWC1)EkRm~XSbQpF-k)WqRo+l56;G-t'
    'YN7CFEpBFWE&aOTWAT1cAmxfWy4e0|8{_iN+xcF_;<H_}RSdr9&~~wSnIlTMixTogv7Vo{%>3$rx~_CptkHU6nNgHY=3o1(9ZGpR'
    '%EIfGe6McFc4DK}Z{fUbXSvGzvR!ntoq@*XV5)2jCDCd+s_PHPcG2pVe4tzMaoOG%8-?bZLx1Ws_)&LcyioIWzRgls^F?v30={h5'
    'U||$Y*7*tU{L)1_-`~Sa)%gV)D{R*mtpV^llZNeBq(#9~&js&A6*Az03L<f8>g-6A6=@@e#c5oSH5b^xB4uM1sZUI9UTq&cd&h*_'
    '7;?cS4#(D8ftFU<SX}AJTo5O50aurn3)}=;=<)_kY9#QfT#()+zKjdv1#^Lqasdu=A(!o3$b_%~7ewC*Z6XR2xUhiw`~_1VPMQN5'
    'FKg;c3p${FmlKdC(#@Cyd0N<P5f|VEbAg@0h3y<rT!?@RT{b{c6b2^m1aen6GziNDTwpJk3wgPW3#sLSZIpL80N&cJ(kv!%0Y9i5'
    'Ea5_RCoh!?#WF4k0U;N<NIwU|rgMR3xGxrqxKO-cF68re2pQ6=-XY*_%LVlBBK)|uGfkHFgdIX!xU$W;I&FvG@8QLIg|elyfCW}j'
    'o^Nv}xrKb{Ea>M>o;VA#7d#76k<E%H<LX)G*5{@OVrY4?&Cl~$!c*yAXn(3}$v)ZN!^?~(BmEPR6?Shv-cIbS^=c)m^~!bh@8bEb'
    'pKjt>+<5tp`;Yd;Z2Udcv8_Qqo=xN_v4Xkzk;9llZX5qm^T^ccv7FqU%AeLB+3}}~`L`a*skTz%-#nc^?sv=|J2SSRLHJznOjrd;'
    'uzqwo0Kf|&CVQAPBvz!0VheU&Y+>)&ln7!Axe*zpFwFKA`_4iLlv>XZkXkzv%$F_~0Ax{cJ=q^F4&@aeTt`gJhYo*t24Y)WYD&(1'
    '@64Rtw~nW7Yfb5-zEb;m(*8P~7l+7jfk;X}4-%ONG3TON$5jF<$ud519Z%5SnVn}J?5xw@VH_fv%NLc_v1i3y=zHzf_e>%D$?>5S'
    '^_<p=;zP;rkS}f?UvyFyNnXvDLhyhu-MVgUo+WbXd||1xQZAY=ZXRFu<?=<v7dvlPo+w+S%=0BTxeN4Ix1MKd28r47<w)F4vt-$>'
    'ys$4gZfEAvU*kGhuOs+83+6?)eybE9;gjhv6D5m9aZ~ex>0i#XXK^p#vssb;4mDID|DA8vmP!~mRWD_Q68@Fb?b)J?Bv&SD?Ah#e'
    'd$uU%%?ECf303Y=k!68BTXbI96wPEcSs&#>;9|dMJ`^u^J}89aMk>V^ybtL8sz@`QB9#<w@G7d~T_}dDHQG^wx*@Eo8#1UA;}%qk'
    'k@z!-oL+-PYhImgRW^5ukJVuDzgWq>9MoWur=vt6$qNN`k1u2QB(7A|NnCIyHGytnT{Z^l6(=X3{p4C`IFzeYNWtt*UaIZcB268K'
    '?mk*yh5|c~E!+1|h~^yg@VWOD``Oh#b|z0FTN1U%sE^~AE!1SB<|T+JvM)x?S$FxwLiio|p8R^dqk|xIMV0x+4XD5-VtkuLqn)20'
    '6Zr;cQ!dIeV@=(M?mpTRw&i$!{ZSv3t?8b))6SpZtgM~e<>9<yaUic4H~P8D_wmK;?je+OHD8byVV-xF(E<1cHM#CXj!MfVi_QZz'
    'bsxI>X!zovpTw8)G=8AAtMk11>3QC`^PF`yjwgw$&&F|Aros7#F2}=^I#GQ3ITTiAZpq$(!Am_GSMt5oPsXS(b*h__iKwLdv!ToE'
    ';J725OnclnBv3A~lNfusHJVfbTyZcv+0xe9{)|ffyhKgzHyLdOQs#FL!rAH!N|!CInw;+TS6d6jKksKt_fB?%+0yO034YF&)#*u&'
    't9M$ApPo#2>KB15s~oJ{uprXK)i%<Ym_k>U^aKg<>9}T6RkeK*!W-)Yt-9d!WLoTSY?8K|YgJ@f{mu4qpQLn?c;o~t$CcRGaUM9g'
    '%L8D3%~BbJJmA}^2D&I<Di4hF>9|WyCh^9Sa5m(Dv#0R@%^-Wqik0OJFY;r&XyA{`TF&QHV}U}Nx*CfwiX8Bxvmlg5B%iMu3+KPz'
    'YAoDW8=c`L7O0wPFR|7F0{(QXTA6c`Ox9VVP#Io-ftQ#!7RB$!ON=@US8BOu9g*ce9hRHHoau5%jq=AGr}CuD<Xxb{TF=j59g!!l'
    'BYUmxW9v!U=&<zE^`sP45>d|f=&*EmjsT+YyC79$EI9oQoyQWDM_!au`B8FJ@Nx-1ps6U;-AB8w=S)5;KZ=GQ#R7g5Gj~Be&FhS='
    ')Iu;npz~O2H2(6*IxCTRsqLa_sl|)k1qoD7`K*&?2KPZ}ecHHW{aq+@d8Ik-m2AGH{}GR|Q;Btp=-*V1dWjxm@JByqL{Lg=d0OZ7'
    'rY7)~L6=b~6n@uDmH*Umn~Eh76lf|&{T?DHkj|SAnX+Y4R2f>O2>b%js~p8$!lup#aG7$jXg;Jbcs?ZaY*_2d>{l6bDocW@MX=2<'
    '1(B3|>U_wh^gLT&!$R_Vvtf}hZr;2|fSJVAnTuIa$qTj_C@B+3GId^{*;}S;(Y$akcwX3f^yeJ%dR~+ol~14kZo7|gqL{o+OI)i='
    'x`_Vv1=HWmTc@SW(!|v3bm{{7>uu!(<5D|SFR6r=sa&*9o8Qkm&1cSs3^&_#=2cZOp}(*0=7Y`?qxj@?S|<_~*{%Eq&j&tpK8T{Q'
    'wVjk&7F5dS-F)Cu8KoxgqwzCt(R|=@<^!B>K9pI4GS{0AMKd3Y1@l48n-5TArrF1NpK(t=@veeMVzf1C>U=QPB+IHsarJWNgV6r)'
    '&EDub-?3Xu%c}?$FTmt|`U|s-7ZqlDMA3WtY`(;=B${e=-F>vN3UOL=-P+S)6=0g^x;Z_%t|j26Yep|QuvJY#rES5>v2Iwp>Dkr('
    'YL|(XoSx&Pea|jA-e;<xFQ#Os(<<-BRJJr13b*W|DBGT0gG?;9AQMY-L}{ke5=vF|IP_Il_MmKH$L+6nD9r+tzGoLC#Smq|(zJhO'
    't33f#YRx@LFMYyhRdg%ST};`dY<qS!zq;)gnG}7Lyxj5gwdh=j&SwUyk<OsL7HLoGr-r4%N4&j$N_>5=DqB$4%KI14u+0oq0~)FY'
    'eb4Y`Tsa*jl(OP<Dl_Xbr@o3*n7`O$2DZQ2p)42VFY0+~oe|2^d!Y>XFnwJs&Gsz3GpyX|+QVy|NK~FI@)=A0a@RVk=J{xHoGmr|'
    '!FyHu^zUp9+%6fIyw>qt6s20?qmgQ!kLD$u5|VOWMO`ZZ>WaFV(1DLYs%>TCLW#+I(S_9sUs6$5%9meJSAxiWpk|y8LhtwriUPH+'
    'w*^&J_}(;IK5R4la#zCS%Er0&?Hy4XX4!&$ddVgZ-`$7n<bTu_Od3wKkHE(>V7IoQon{L*HYC_xj*M2C?#11u@8qQSRKGVnTFRAG'
    'Ry)!?=!hb_xH}R%6_Yy;7;Y1hEV0LB+sR1}s^9C=;_g$c8V`AZ6stbpKAvKai*lZBN_{osrrNjE!TzX=yYn2lm^>$(#BGdOqMJnd'
    '@~hvALgdEmtM+YnbQ997>OxTUU=I1v#oKYYz|GOz?tcsRsZG4SyN`ws{`r{S<~OVM&6<5GJAI!jW_E7M1gk4{;Pxe4vqjdgC?qF$'
    'BY@l=^EqZq9h?{W%U`qAO#fM-IMg;Rce?EJL2YeXo$7pY+*jZ}6&A%;)C=~X;k=qf|I(oN%bNZM0{VBht28A~<y86?&L7EJM1T2$'
    '=`ZH_^Q{tD?LS6E6!<UI_S9CUXXK&y({>Z`9uDm3l=%I`w-lepj|{m`$J?vLwa<@j{oRt|=3;WZu>i2?B7X2l;wxptk8%M&V5WX@'
    'qFEmbP~rN(wv`?<l*Ls2lsdfpqOR@=Ua)>*^L$PkMB{T}N$uzD=nvb<S-3fze5%xHl^nN|4*8rE`~Bqw$#Ukpk+8zYy?kXF2>03D'
    'zRrNji(>M+A#+fRDnQ6`o}M~aMYG>RPszFYyuOpTtbMa(7WkgBZ3U-<<>}-&a9O5qksT#pa6Ye0XU+$nih4d2{`39$kZik}C22YN'
    'yoa?ePm4wKA^m-<+poTRm4EtLWZyo0`TXiHugb4qet!C#eEamz0^j+Z{9NFR5APn{K7Dxq`tot}boc#VH&>7N-mk^4zt-Pz#ujDH'
    'CBFFWlm7x3v{8ls?*i8tUzXs1zx$t8>6iRp`00weX$!!qvS?t5#Hbv2#<b@ZavQnCq1VJRDT<2urS@?z+|(p_(v*@fJ@WwV=w0Vq'
    'wW#z()%XCJ6ABpLC083_JJ%Qs)dd4^hcA!*Oii5(xb-CmMyVrkd)^-Z^{tRw>hQ8mY~hy<Ehke)zd-7w;LEV=ksWEXDyUhPlI+P&'
    'A&n3|7?4R;PNWXJIO?EThK8ISr;SUBDnOkuw8nihrV)j2=GnG>lrqhLPoqu3UZCW-N^;CNb!;iBBP7<8nj7EbOJ<%rx%ItTYTFX>'
    'iIS7QK<d~^C+l(Q6u2B!$u_9+InFD5Dt&;cO>-HhzZ|4a`U0tADxJJvcB+EWD$7ctw_2x6eSvgQI=`aXiPR}xAa!&#v-Zdinru~~'
    'gHF(H&bBE~C&`X`fz(kIb?m<NoLB3)1yEjgTCJ=yrM%v89G9VqdMAMwNF7<ttUc6GzGHjp&o!0a>C}~5J4Gue`~|M(0@riB&rZ&&'
    'G)?@V6}@?duNvn>DVn6aN%P9SK*{0Nie>ldWLB5SDN|LoUv4C)E#x;W@OMyh#0!)hK*`y&UX^}h=95wZa#3zq^VAm38BzL_+sW%y'
    '_VOeLv_J)7Q!uQG=G!KAyYmhkzlYZ0kW`V%O#2c{zIl*u^vzQImwT-yr`{RcO#tZ937Yp?herE;>+0B+J==8$u;%mLt<`^BZe1?b'
    '^)g$(pUV1?d7bOYA?wF<`&j>ush^k4_mhTHqK7lfGaRCqPK8Q-OH1V?hZm|Cb7hn{nEq?S=ZWSyqaV-|F!+NGrNYO_^H`jGNzu$l'
    'd+0+uj{fi`%Av!oFHM01ZQw*ZH0;Rl9(s&w!2bJr5yNYAfwnVRgQ*<o^YHaOqt)hk-&LWs>POLHu%@Vv8Caw9Ru@mx=0kV$A3>Yv'
    'z{X1;!eMzEE1kG%b22S3lLD|@Pn@L9hvk3T$G$Y3s>N1qPOQx}REIabY7De_`1%oTZk4Wla!wb*w``NCa6Sp5bXw=-REqpjZF9wT'
    'w=Y#u?SV}-e9m2SsErd#5%h~f{^156JWd_iBHR3AZ9YsUZ>6o1rd6B2Ty1W^H$h-h@MOo^625apqr1d#uhDs07*M{*SRt#lHtU<#'
    'uHKfz8l4r%Xp2Iv!`Ft-!P>gSxgeILKek3!gU47j`tZ2i5sltT(;rr&^WTL==K>in^@v6f-#MbuOI>U9QnM=4D-~H)z_8!gef7BP'
    ')98?nYxFMlu>I!Xd0IxHM^}%_Ngfv}8(rgQn``QxhV4sJpvh*~3#*Mz?r{N;OS7ZT!`F{!^W5mXintr*z-K|3ygK%iLv=2C)#it_'
    'dA4fvRhvhv&1c-#s?CYDxd7i}#UFziMnn6rAJOKhN2}7LCDW+SeNm*WYAKpZ166IX)!TAFn`dfVjtUt{*zmb*%Wu$oTi730o42`g'
    'AZLD&$lJ2hBDIk=Inv<o59MuPzXxv%E4`OoBzzbT9lmo!qYI&G`#e>?u$nJJrMyOO8_CVk=!2GXe*}%*Z;IE)-ZsN)$ME^sf$~+O'
    'KleD*ecrY<JVnnevCsEu^u9FxK_jB@^1UsrK)tPaI`p;#uOHFoP?psxX^SG^PrB-qRmJHNp>$zIvD)Vcy)C_RYytLxbhTyK+R>FA'
    'T(vpn?HA$WZ*QO5NuQdl&HK_6XfZnn+3IZ}*5>&hZJy83=2=w$$XQu{&4jVFHa9FQe93}UoBtNtJY}mkU$yzUw0U2eR&D-bwRyHj'
    'n`hItxh-XNroSj$=4<q*qSod%NtsSpZT=f+a~_R0hgF-u6m7mQQ?V~it2TeJ+C1H(&C}`H+<>ktNtnX%WUI|rPs?hXuiAXI%~x&y'
    'Oxj$qWc-wW@cL2P+||{{Y>wKu5|!NRwk#>pSf8WKYZ+Tl`A<3JFYTJ87?Bou;ivrj(zKoneWBW%Gbi$$9L4^tM>Kii4}Dg3B?T(('
    'Ot`#+s*QA#7DlZZibpaO<+u#V!HNFi^Hemp9sLRaKd@ci<qOWu6OAlGv6H4%lfPsyi{0a8vD3XQsg+q<*ItM<pJmNwS-mVT&C9ap'
    'v-~dXawGDh*s;sEuO9QTD6n3WYnCXXd@~=D6iwwVwN~CbqRCUsMjK1#z=D&X!{?=1?eYlBavna$VwV?<R24(%+M~%kX<F^_mu#2o'
    'J$AXCZkOX<RhI#)bjphi7Xc97E^oUAt=jyzu*<tP-m6`{+U1Mw^1d{!cKHj{=7K3-Tg&jB=x6`+Big*wCh@j;=6tUTuUT#4edak!'
    'tynu&9P^o{<EPJ#)=&gi^%z)dD3XrfOAW<FnpWHV1#5GYYLR6u6(}NuQ~iT?j@jp^zgd>)Jk1^R-j<A&3F=3yoU?kWMwkCTdvDe&'
    '$&RB5{+E1i1hg;n7I`x=>vqLmIwEdj@+lyb$$$i=tAMUV1C7D__aSAAn`E2J7xQyG%&Tsm@WsqXiuy!S6#0YZvy9tlk7?hkx;57p'
    '`?SxWh6Fn$aEB1tRrxG=ll39CH`1mP(cdeg*MQq5wtveJJ^N+@(U}E*(_>e;+6VwJW@``DIy0<kB;6A~{}B<rX4fG)tIb)b<=rCs'
    'T(7qy5FMtIs=`d?ijg**i2hy?T?Fhf+X$~_dlNGk`^5zbY#Gn%S_zDdH%4M&Qv=9WlfvG_HK$d+?-#qMKG4dH;}Ir&7k8KyHDy5H'
    'tZZmwWA~+)xT8n1@mN()0K-m_P$(Pm?qs6_toUNqyUV`WumyZAYqSMCRgMbJg~7uPf^jL7rf0lv!@H~JZGo*WR%gw&H}Sf%ixpky'
    'dcMO1IBT|@wm^>Paw%SyeY1h+k|`MxoogApSoz8#qC4tnb;j$?c-`sUo$<O8(I1cKDhTckon}WRpD#2nxzugr0?|D7Ji*<Uz^aJm'
    '((p>|?RgS@Ff=C%*-<9@G=J}_>+AB~8O_;w25t8lv>Rh}TdTnmnp<b#H9bu{)}|B9-z}Q+1vKY-&>RbHdZjBZC`0gKHKMt|;+!X%'
    'pJ;xf`HAKynjeAYYyr(#IhuRUO`jQsHI-}8+U9%p^F;F#%}+Ex(fma7tI?b;pgAo^b781LG_Rbn(Kh$2iMDxN1>;ZK{6zB;%}+Ex'
    '(fj~3Cktp!%F$dh&JoRB2pX$!_O^L#gQa?Jj_Zl$Cz_vVexmt_=KImSZsyTE`FsP-E5l+=3ubv@bMPL`;h)md6U|RFKhgX|^ApVv'
    'K=ZJG=Aj(TIj0fL8P#Nr=FA(`@Dt5XG(XY&MDr8PACBg_u9tGovu_q&mkw6KBBB$=HLE@Mgn2~tD%i%TQmLFd=PB)H&iOl;NsEYZ'
    '3nCW*=oN^5=A6H@eeM_RbHB$vCo!+3QOwZ#VxNP-E*U>}LQnhrw9ilb{6zDIqdBjuc$R<Ck1+Xs!#1yVh<#6hbxra3u%#N&JSbmT'
    'wHM9LeuQT~!q>OW&whj_nm@occieNw?8G)7f4+g{TQz~o(fmiO*AiwL3Y64WuFadN*K*cZe)sj2$J&&j*bcr<G=Dmp+XXbY<!HWD'
    '#q31$6U|RFKhgX|^9Q53uFYa?WwWQYvXRtb?3}W|u{R-86cz&kf1KgfSzGzK+R9t?6wlhqZ{l@jJ;k%O@`>mVKy-~6EJDFLoFjVr'
    '%?6??Wi{I9RD{5k=e(lCv1?BG<F-4kez5+86_s<kw3XYU+_g1U?~dqa{Ct0I%k6#0u0nL&4Xx}nw`HtNC!)VsL=V+s&GTwc&2uN}'
    '*rQN7DxLROT;97zumB+E{24<(Yo4Dr`b2DJ&GQq{?~mwi5z*ZqM3>CQx{6-H4Fu+&%L;oGR+2iU&N%vs=qI9|h<+ma0f=rF5#8>x'
    '(F13(Qm(1J6P_v81Xsg_l{El^r;UCUqKgc{#fj)|@pWYm`ibZ#qCWu9&0=37v*(Oxt!s->7hiemw8st>0god&McjEt^gJW_(y#N3'
    '=!xiW2hsH+qU$|~4*KcQMwb<(j)9HN2*o(M6Hbb7cA7g8{Y3N=(N9D_0MVPJ?8WSx4MexD2{9kNkz8BP3=d5O_~?V=h_~fYmmd+)'
    'm$DbP5S{rmd-44u`kTvM^k??s3m|$}w9&&J8$Ea*vlpv|*HU}NGyuF3tcL4_KW+5WMn4h#w9!vQe>|c~LIGeDLZZNwL&N9@6eUwM'
    'M#m|05-`(o$tplaUU^mlPHWNt-p<`zjz86iT9(O4)e@AKtnQ)Oqj{o0XPYY2#!x+Xwuus5kbDzQ(~5>NW#?t16caID)6`ZnSWld&'
    'Q8r#P%i$|Wt3aAE**Nj;WTT1TwIJLQmD>W@HygHqu5|S7z_YW$dai`59Tkizt|&dTq&7|)OKRp&DEHm+_jN=08^9owu1S3bqnS!Z'
    'ulX`1EA!0j(Wi~~?x~No=|{2!20eX=x^7_V)t&^N*L6!i-$HXL<9<5V%A&<UD;uzO1jFo~6U{f!98j9i>Csm02zYSa+Ulog_r%vb'
    's~xd~=DjwZp541fbB0!U&=WKtf4+g{fTQtD8U=ur8f<fEEuwi1&YX2;zUw-g+xj{*r>vcS^hEO$&2L8YUYkxdf7fVE5w)i^my^#o'
    '(45((BF-z_D2EX%=A1=rYb<HJJ*xnnHJ4xbb=F)y(fn=D&m5n@^7PXUBsbC$w96e65|Lb}N+GT};T&zwjHt&TIc1c+2@N`t`~{GF'
    'tW779zf-$h%YggmweWIokJ#5Nb~)i3e0jiW%dNq^%?d#aen<_Ve?9AbPWFf;Hm2oMdBJ+1AH`xEkKCW7lo#$1b0&BV@Z02GOY-@~'
    'T32hL+D<V}2jxM&O@p0cXr+W^=Z?bqT33bnQQe9`dEbuvlbx3{2K6>$P&@aBdu=+`x_7+RF$NwA%d>sPpKc(z^fV&5H7W#(NKOgv'
    'CTPnmdG;09+D$N5B6-~-Ibl!LpcBd8B9iaiP3X1hMDq9SwE$>?{XNqsCjVvw(V68k=D;G#2+wH{8vPqn1AggUh%SD-D%8QvcZvar'
    'ClP)A{;Y@eo&o*(e#&P(qzCHpdq?zkA9&_uUiQrfqASJYiI1jc+9}UClNu}B@gP0CJ2QUH3U{yjIxF0rHu_sZbj}D`;&hUYpM1W7'
    '=Cy9^b1fwY$8CtXh`I{KpAnaJG#A&#&Z{$aenwpGh336BooN1^?Q`0o70xinB(u-6Z#ED;cwin7odj2h1}t(4dV{@rnGCEs5q)Df'
    'v?f>e=Jnx3^b^tVhUno$^!IO{(=eZrpM1W7=9Qt*K39yAT6xA;Rby_86Lq7^na6o%<iGIi%*a2{{O#E1HP$$oi=SuTY#=&uz_|0O'
    'R+TcfXGT}bRd`}nI%Chuc4uX~6Va#k%X1L@tZetvi0&~?K39D@`(^{tb*0;iHqr)TJ!_0%71-#NW(NMAHu_n8`b6~nbylA~5&iy%'
    'UM<?_)gBw&G@P_G%9wS;GcQf!f?(8oY3XUBpEml5=%<Z-BKiS{?v}C^vu`#KU3w=l>Jlh-u-G%>m2-ffwGe>DXV&7GwfMrXGi&ig'
    '^tXfPcF{(+yKHpnWvo?J!L`maM~QY8F4VHA$Z4aWHu`C!pEml5=m#LWSwwWR2hkg4T|{(gd8jehh1O`J3r@YRPDDQu{Y3N=(N9D_'
    '0MYg0&ZyqEGg?_hbWgRdjAugl%4xx*V@)N_ozZh=^hET@>)aVV5&iCn&K7NSw#!DBOttywwbK&t$<tsexR5F*=$XBE+UO^upEml5'
    '=tm&>qK(dW+31xau}duzQcLL>55ZurO9MJ$PaFMFHhOq7Haa~K{k_=ejdxbl85=#EHu?)7x?Hr;<*pM(SgX@{<+L&y5S<3E@r02!'
    '+8K4)=%<Z-BKm2gpNRf&MCV+^zSxrr0LkYYXdbAp5zQMCFyg{ZV;EM@g^O!bpY>ceYNGQiJFM!n!|EG&y-J5weRf!V|Ms~O*vUyL'
    'E9N>m1q%2MI4zY4tO3k~KUk@y29+=lF0o$CcZZvHa<WcNDwm+VWOd&T4Gd6^H&v*Op}LwG4@z`lCnqcm%#@s$O`~+o)nr^&TwG)$'
    'g;$k_m54Qr`a;==cPAUI7zLp$NryI4x0$T4=!qLON54bqPzu(J6Rw)q9mP;Oh^^dsj{OIm5=>ENI6OI!s+wOPW~4)1n3E1`9@qI~'
    '7Uw9j#nK@toh9Az=sSRP46Iwc0s+M;G<f!$R2=)q)s-Plp>*W?(;eBwnWdLzmWVT}5@3IVtSahg#jcc2^ZukG)KWw#`)0!j@tnqp'
    '5^+`&Slcw08Z$GwleIHvMCptuoe`xoqICKokM}`@TsjY%eY1h+w4u==7rxT4g7O;dB1Cjn^U%oiJnVJnVR^PM$j|ezZ}G*hgXr@-'
    '?1|`iM|35y)3sz(hUe+$oA$YiC#Mt%lH(o$rxa_xt6-EnJ7901ITbF<>QSa&;EE^nvZBSV&xz)bV?U&Si(gm!R;K7zd(nKXO$myb'
    'J(Qhj{!}#Qf?`|+d!42`zRBksXfAzdi1kX>wxPju5dyP~V7211alAg!d=1U91oxaCxh&5ye@{&})7X=>=*LELmi~P_n)ljb?z`h_'
    '#zy}SXq%IlK=as1kJAa7k3Zi)bHLFME01YjaR4s>^&0meG&7F7(>C9Tw5WMK+REQCw$0o*^LL*5dXfB{UYpKH%X^Nr@Mb>Jl6<~_'
    '=75YUX0p_jaj?xRP8>#BEWjPtCz?Md(&Cyk(sD*x?iFbnYttENd9SuP4;WFAlSoVQ`DUa=Ml>fvDnUI546kC`oKea6iRSBQuJu%t'
    'igN48o5`)Gr)~aTZ1YAmwG=av7INm+zkqFCFWBaFxoxggy9?SVW`y+I1E3+A(^@mj&zzQX7xc8v-@0vn?t;DmnrpdO$w2O^WWcP7'
    'ryGQ-R82e!lF^uVPO6HY6@kyZ^OuJ7WkguFUv7S#dFLmh=ZG#A5nb#<bWJ0o>xNarvqpo_4!9RAtGqZ7{Y3N=(N9D_5&Zx}=S%e?'
    'vu`#Ky-_OGr{P}3?$<_gkJZMQ;;Ot?>RCT>AEKW%-rqB#pEcf3M1KIHvqeN_dk{TteFCD_4I|cj7OTBm!DOJ+R41Z82+^CfBJhdm'
    'dl7xHB5-pe`U@aBU5vWWJyDlHWsIZyO3@~G)>t0n=#_0e(`VG>jJlkNenwqRL_Yx0$x{86?3)clC$6oEN15VS1x`^O>$eys-I?oh'
    'ZT%LJS#jd5-|`k;Jo{TJwzGcAiRgDnbkQtDU9xXB5ZwhD&xvZP>i{;oaU@`!cP45o?HP5sF6y#Xk?V}QyouM96}ir+%Zca@K=gXC'
    'YHqzJ>Oz~wV;vVS9jPlobihu`b<s^z*)!MWjJljrmow^eBKi@CUM<?_)gBu?z};fCed(%(Afi_sZFFO7U4_#|KX*n?L_clx6VV^}'
    '`qO{=Q~l5X75u;c`Jeysr~m6u|N77G{{Q)B_>X_V=l|jUXMm5s{_^#2-~agiFCV{s`u^LW|NEz(zQK3@75?kL+AFL!p{bdG5C8Q~'
    'ynt#;1;_vYK#UQZ|9}7O|NT?-pY{KNA2+;K+#_;vf=7*+;1x=c+E$VoHO>F}&;R-TKit3m`M*O(&&NN$eC&z(`1$i5iY(7bGK(a!'
    'LrAiON|usT0ZEi}Bx!Jd4wjN7I-|&QSYTafDI!6rfg*kkMU+~Rk`$g!l2R%qsd+X@jI(s$0(m+~Mx+B5=(9=UT&EPVr&FYDib{b$'
    'n<T-7O-T|@Cn<w~(2SwGvdSHelTxrmNQ~Fd1#W4XOk_mpvq@6fY$NXJ6qyXTseCp`n$uKDR0By*)ora)O``tU6d6XdaSP8Lw_KB0'
    'GHg#Ua4lF$>9}FFbgbjulGIRZdy?ou1};EAN>TM(O~MCdUI1<{Khq1aSUM^--SC{jGgS#5WO-@=;9<7sl0>-~<K%)LyZq>HKmYRS'
    '``3T``qTF>pZ>?52XkV?_Jfxk=;X0~eERxr*Q0ZesUfUkq>GWxwWJX-$|J#zQ&!cAYNl<mj6VPN@h{(h`s1(PfB*8^Uw{7m>FXY1'
    '1(jp?83H6h*w7Ix7DG_01TV?<HgXM1sb%p$B1D%EMPtNx61*mKW_N{cgjbeD{`L1ypFe;9+i!bFmt5qe6TtSEmDNv4LMzoC8|B?6'
    '#<Z0J`@cs_TA56pwwOQsN1Y~A)JkD6z4ATnqs%nA8YiXQJ(#Ik4Y~vO=(!!mOBe3ZmQl>50rzXS3{0W&jij<iB1$F!mcDQlmfMU}'
    'Ypmzk3<Tp6-X+}d@#kE%pIe@O4i-`Sd7XZarS@Y87u({FKBxWXa`-%cM|syEB{-Y>UbLS}Tm#0>)$Qk%$>_1&{YCm*(%s)Q+3#id'
    '`zn<~v9d;t{r<O~|NiOA_pjeRe*5F=_h0__{O#x8KkphQO_Z4#rp?NzTRm#<`q(o#h^6mw2n7jx@&0RF6X1IqGoUZui}ZU<<GFOf'
    'nOnGn!a;`FWEZ|?IM^X9ehWjsOdSq9aL*UNkCm-7oBO_SX5LE$G|`(ddku*0A;Kt<=wTeq4*mEo2zm_KStjIUm0enxbhv(D+C`Km'
    'GM8z;qKMm9l%9=)WQ=?1X>hDk++*5Lho8<-;=QV?8rEaagC~tM0uy7|#cqjlJ>PNCeX6tzc%@d2Bi4h@?QpA~5zh8u@^8O>|K+z|'
    'zkY-H_{(p9-^ZM0kKRYxLk=}bXawOjO8b(`RxIuQHAp>qHBArQbniGUsn-poz*rW3m17N)Oi85Ab1f<GY<y*5nPLD+8P84ViV^pp'
    '`u56N)d9o?OPh{Y;x;sHr5>SS;C9FdN4xis!?Uo`{kH@5P$QCoM|F=wKd5{8&<~0o<|<{6)qST@JV4#yiRQuEM7zk*hCg^8Z4Wt;'
    's|Rm1?xMy>@!+l4J>)2sZRg#8vw9afnx@p$W8l_QSe$9Zan0gJKl5?+P8KVk+daCyvg)pss<C)(@(94zFy;?VQP@L{Vf4{C9J|O#'
    'pbHT@j`@Jt<zqg$60@0V7sM{sh6f;Z<{st3uQga#l~)bwI-VT_?TO4*IkQftZA&Eu2OO@{%y~dt&f$OX%BBhWD9Z$#Czg(7WKWPP'
    '#tzDv>t6$ti)-&rw(mcpVALA*;4H0O<WQTfc4myAwFWc4!ipdsyhqQRGy$6|*m|O1rW=ZGK$xg&yplGxaMH8DD}h%YpjZG%nK`c$'
    'hY=6~XS1v*bs%^JLU0Z66mp(?)8&e?QCI=5lnzWb%<J}b1vX?;H%CnxMs1FNal{7vD<838)|j~n${7C&$MONQg>hvboEWo<9A#Ii'
    'u?~!X5R+*n*I42bzOTSHc64HHROvWOt_)7#l}9KPr&i}0r4yIGc)s+nVcsnJK>KFW12l{0o6;eSK_Yk`7m5l1TEaA98U{$gShAdH'
    '&9a8zjgJ%1*x1B?HI!BrMl%RZ)Pq2R8!aB3E47Cl!SzJNVCGy7)RfPh!Dy?tjJCo#^#IipD)VPk=`-6@@dSUPoMfIe=PYhj;Lb?K'
    'Y?H33HECiE-B6o&rPMZVavY&j!W#L|e84@#NJ&|)P+^Q&<<oZvezPsxap%N-fMQ9LCLAVXU?d11$OFejqH<s}l&DrBXW96af9^~Z'
    '8FNhIl_Xeqlv*h&>4Os%cafuP?vmi-?Ol=`Q+LpyE#s<iQa?bQl(j3OC%89PwT;!$RWe`}psR#w2`R6%KY`eBs*H}vTLC+i0!P9N'
    'yz&Tr(k%05?w^ypiyV_|?-0<Gi#C<d*x>+{-&*ww=kf!z$<S;kE0w%ytVA_erUspeM?mYytjU?JdQ+<7ylQOh1%mn3wDMp}G}bo9'
    'sFM*~J~%IT4>_1ixk655sKminKvk_^)nip1r>va`2PIRM3L4eMS*6gS0n>~fHD&RrL58`AMExu&$D!fhfr#~4QixCwm?f6Wbe2%8'
    '6*Ah)1}d?pHb8*^8^dUTgbJ9QL@y;7()ikCq-k`l-Rg8@z@t(U1nCbMLG0IK9-L6WiyWKp>P0LXV7C~F`d2kuaAK@bg&1{zh2j*J'
    'jTPDJN=KuWOB>s6GzN<i0JD=IDzz!+`IWv=ygCLFIMqz$kPt2-SdMd}$nXXv6e8dQMv!rq*<sZf5)7=QaU3-6VZb;@)3^Z4`iWg{'
    '({QE6oJF`&Qq?#ZL20N%NPtDl9F*U}na)l~P@6C(eVmKBf-wfv0*7B?4*@rcR&tdw7i!kd;>K2}?h<Ssi_9ICyu&foF>^y{TKcIN'
    '&M$f5bLA=%f1wQMAE2l_+iay~Jd};Hv8}R}mWLWAC9QFj%uT|C!KM+jrgHI0Bb;vxU{ozCyb^wVn4W^ktsZ<zZ5KIGtdXOu%0?Z4'
    't16I~5Wd2UDNwf@)pd^Q>6N^80k1ql#**aDwZ_Hj5(X?^tcHKvEr+OZ8GFEV5m}}LOQuWAEUIG96m-<U4h;tPR4O`S=_US<pepW*'
    'T3}34&nl)V#?B8JLTUAbPX+EFN6|d49M{ePf6Ld-!Nay&TNgW5)dwh+N{{xyAjrgrARqyl;!cB`BR!+RYg}}yNs!7=QgzwX?c&2Q'
    'Zvy_SxibcLW#DbB0@cI_XQO4~4+3Omc*>+uV<tV=xsg<7HEF=$=2Ew<Dsm=ONT-ivG@2X@miK}y!G6>SrS@<wc!~)!8M&oC*41PQ'
    '#UljcB{UG(!a8`Ez5=C$nHcjLz*;zH(}^1*R6ZMRG8>DHy~`<}&Dprm41B<B)F#UpjGb;rV>;i-wwf%}l}~4*u_6YBo8V0aS{fXv'
    'xQb>`WWHgbz95W4##Ux&yZ1jYyN4W0CU&<OYg)N2I%KKat?i$kR_X&Z4J`09%o4l%T(+ziy7zc8NmI9J?1-Z+60ZzcQI(ro$fF?9'
    'YNj82UVR5S;0Cb#00f%eV;i;9^dA1Lw{6rSqx}9VC15qoss$wB$feT6eqyA0o364H&lY3jks9~DVL=jAbx=TAVAY`qS7q2k4&}yX'
    'D#a4CDt84&QG$(tWTBJr0F|Q3=oRTN)kgIb>r{%A^Zd%dgmK6CJ!rh-LnzZ4-=#M9;Ar%=_regeYpwAI3@KAdbs91r9Fk!MPYXuI'
    '^f7ihrM*^oJH!6XJ1rM{g{6@IO?5F%iw%3SMfN7{lCmeaamRPv$*<f=-ite4<Du&Al*00zSUU+SYQ*B50<VWU0h=_@Skra1-15<#'
    'nmshRW{IXc9!mGBj3Q$xU!o`}S+vcY$*fW~x|6t@yuq^`>MU&2q?hHLgt%_frX=2ZlZMm#(PZy-CwDJ&O7@CwqsiY*;&)pQlJthn'
    'I|;K?bQ<o2M`vmx%I@R?@#$~qfCLQ7PlUqzR7>}PxkB%y0}R%c;GDSiPQV+WxHW~m)j4lHI>CJao2pV7`DGc!Vi{HON<deT>2B*B'
    'QTM`KEHg6Hli8%Hk*S=<YXRGbmSK7B5_7K=6U(IdLY)LNd6BmyjqD~2fXD0^IkGZxe%GDY%AM-F(G>18a&V{SUU-6~db}(gIiAIO'
    'N3)j#R#M+pYTDMOW@Q}!tfbXl?t~SdLg}5TF>DE&upH4)Z)$t?T1J=VN|M35O%tPRkvl*+7GxoYJH_gSJF$CFlpLbC4F`axp?+8a'
    'P0Ona7JC{hd~M!|H0hoA_)ee$LDIstw{9q3;x0MIbkj<goNl|xB1{fo-bRzT+npTT=`QwHsP1*A8stPPT8Nm+Ej6mmP8DyDUA;VZ'
    ';2Qd1idO@(!kxR@oyMo&Z^DA4wnB+LUoGCLzL#buB{goNskzskk|HR#-HG1oPDx<-rg&OX|K>LC_}%U#?sg}6H_TLbLppUYd<ynn'
    'Gzobxk37j$xk=(lt-ITz&*DBb#Ttj3*YgF$E#9oTvN4kt=>f3Vyibj{YRWT*`qz*_w7A<=m{atCtr?!xN(OdivNKhlQ#813ek<u_'
    'XSUHJ*tYqWYE<tL*QHrE!x<01wI6q7KF$NU7n32UW9G{fK?XMMR@Ql8ipV3FH8ju2Nc$_7Cn@x=Az5MhG)P(c!UNcq`PindN6WX*'
    'hg<=%m3~sVvHl2V4O`k+HdvRYcW<U+p7_x@--eEsFTA!Hi*W1Ok)eoFD^{B>e(uF6m`uxkG~;IR)im>6*ZSmIc{R-nw}6dgRmqj3'
    'z<5@3eCx{5hA%#|DSzfD=$X|S-@0<NrJGei-=y}kg$vZ;rtOsy8dX)_e5M{rC`&flr-f<m+dfUAw>;P0aIL$3#-_&yc0SkNAgk-q'
    'Ejbyvb>%1&f=_MmN`^u1f@?>cqVQA}XAk8?S5~7dHKW&$4~wYC9kaWyWw^P?R1v*(!YR&Klv2r+ethM)*8k?5rOBMV0fljc@+yoO'
    '^*z|SZnPPR)b2xxFw%U58;)1u_oxrUCYL-J6?f%)QMiFvELk$5RpEwV@s%vOvcCG6;Y!Ks7(c#lmL=UeHl=&n^24qihzq*y+Of%L'
    'li(P`*&@_c*CyRUwpa6E8!zi4vZ?i#ZM&?%#pW|Fn_@^W&Te8Vs*A?;vN4yGp4s)xqy*Bg8I$yS*?#5-0h2x|TUU-Y)=+yz)Idv$'
    'uzs|aHmM@EZ~ae8+U;Ba(~65bpKETo*2Q|eSFOdNy8hZa@+%Z}BH6xnw9$pvnq6|P$Eyu)W)<U_(c>%Kl~*P;jrXlLxH$zJRE0KH'
    'HIh+%wN5D9e!A+Z3b&iCyArpTuDp_7E2A{9vdhC(xM6f9z5MDc#kHKKJuP-3gt}pttE*?K#%-NzpDX0`9!9!ZuuoQLtDK$j9&zP!'
    'hb~NX{HvL3`YoBlu-<hWFyO~1Ay;}bEY;GlC(&A_(j#Tsiw3U*>!-#m8yUhOrxbxFO|v8S8<n5CTC+8qDQ=e>+?JjgWXjbr!|^zw'
    'wHB{L@A{B~+rS)5J+azTp?u7SoHVr+VJ{rbdk3A7U6plvTCbSZ7YwN<5q2fIRzLkQT3GjEWe8VGyfV1j9a1q1n6gCfDHzkAFs;Q*'
    '3#&vyt#fhX2gQNAUZP=f*Q==xsw{xaDY@fBVZVJ*tDHB{x3U{f6gD;P9O;S*JkqVLc88oOL|=zZOBk=$#9qXdVGEONZQSlen+Hrj'
    'cp#rNn=WrA{OQ{tzkmPo>FcMDUw-<x@BjAm*Kfal`NtlyQ!=h$WvxzfX#37x{ol~cHS^kjS*Nqy-0ptH?7C0<wI?^f7}n4{UpK!5'
    '%v%{-9BZx`6%++TBrrcEc5}l|G{+Xd8h!)cRSZ^6)qr&tu<ti~La|;rd}fq{Pi5=|4)64E1>TzxWx>P1`@q$3U9B~K0;n5cmGOe&'
    'xA4rM6kJoocOL$u@k#~vk@0;{8h)kYJFhujfhAKFd<>KVj3|M>#n15mk*fGyZQ-eS5FPL4;kOO^vcF&aE<UO5Xd15WID_vM9)lM6'
    'OrS6RrtN(WpG){OaKLEA@IPUc>?p6bjrT&1@mhF3{35W+Z@VXVzwz<Ds-+@6%i=R5zp9sEFKeZ-|9a%ViQm%r9gZaSWyibWuXy|w'
    '$NxspwfGH=HI6n)5l4EEQ#ZzVhfW?B8Bw^mNNBN<Qhah8bJPl?13oj|Rq1mnj#Q#Q!}pTMv997+;2rRKd|K49sGsnQIF58eS;x;X'
    't{k4<aR|~tuHb*Qidu=BiJUGN1&R{C$YDmic`IY&eyr{AAB#_xE4oeuk0WYP>(AFy@NO4wb#9t#bBQpfvukm0+gii_e)$J3@xOzG'
    'vCE>O(#l=s1(z-RA@fhHH}fpE`R{K@F);bru1Yn_Hvhm_*fJn@dIJw&n^`$#TZYWi;u&98T2HV_j!dviJVl13vjkga+<jl*qBoQA'
    'drQbs%CkI}E*9;L!Jd&3)8ZP7ILBc%#dOXp+ElO>auvVv?RU{~!r#PS!`dWTyFs=ViAJjd?LV{!x>XVF4mq+zV9nFIU0u=I09z@p'
    'p%<%cW+lWmSt{_*;JKFRNNpW4xLdX3dqADIs)}ySM+>!%R#%Aj2J3B~ksYGrU0R!`iMAFII&v!py9S<scED(zkJgVudU16?%OF~5'
    'g5iH)pQf~s&W5a_4JzW=-`R-K?r2);MWg-D+19Ov*xnERYw2p`6zPti`6xx(+L|Dn?)S2nd!%{bPemJsD5uf#8rx(xK0oxjFhAaL'
    'M0k|hAdgPA(W<@33pfhB^^eaOJb>n6{Qy0KR*a>AR;gl9H-_s+x>Ltr;vH%H2Bp$k%_v15t@KuYk?(j7Jbke7`ui}|$sm3*THAGR'
    '>4t$Dw0HSn+sB!r`k4}K#n$GGHlgZm`ODp+4v(x#g_+n$qmFmO(%7x+c+`=R9<`o99J7n;v>J_GM`6#EieuD&-}@cIOdfvM&fCaA'
    'FPXU!*OxgBqY|m{(SMkiIBm}Xz&oKki?<v3^_kjP&GY&Jo*s*%WqVx^NQKr&H@+M59I)}8Z`Y~Q+dt$bFG$+{FWs|R;E0v~`pMQc'
    'Xz;GY^yMh*uoTa#X_}Z`6rX*7l_^M4S(*!yTA8l<t8cS1$FhjbyTM>&&$ck5es|iolbTCJnulcEE0MjIf!t!n7F(I(U|b+^RTt65'
    '8+*>Jl^1lkZX}kbVf}Szf%WTngX^i#F-~MN#E;kj>w$_<wPDTUh#I!F72@iaT+>;=tc|b@k)d{V4_(|RU&FMPovqhm9@=cQvol8g'
    'sV?S|uT!dD?=)IkIBwB`@okK+weKP~wu|Z^Rc*x3C)SMa<kPL&(IRTU>DT-5Cp!Kf`R1(!m{<#43`6xX#dv=uQ)^u4cAX!s$`h$w'
    'VqIFb(K7f1ZC-f(U}2zDRmWH>MvL*)k8o(m130yv)gEHpjG~^T_DcNyK%1T&eRUaMI@rW5cRcDulyJ1_WD*g)SU7zgG0LVLu?5>^'
    'SuYB#6|L6Mi>nTO<U6+#l36{>>6w`vy)zyy0+88T<Kt<z2iG<~CN`wCkWn?9ODfE`>j^hAt0W!%=dyG^I57tM0<*>TtxJs?>q&9^'
    'nxwt^a7z`h44`LHdVqCZ9n!uPSdx_Jnf+8lmUdRR!az$qu5&x8hVW+I7~;*|oz|mwWY5>RV|@+gZoQi9wLf(M3%pisI{m0}eaX)E'
    'Blo?}UGH<(`$yaL-Zy&+t(VpcYb~;$fBoxkR~ckdNIA0!XUO7q+|p}fn=apm>z8-V=9m4ew&!jLvb^<exR*;vFwfaGe6!0wz1y-+'
    '8q(A;@JPF?=Ee|@T`CesbpIAZ$(HLa8?NVe>$%-}Znyqu+pV{5y_Ns=xtqF2nstiIZF+%SwY2@UxO^3Ei;2{FYuvn5XRh9Wx^CO-'
    ')@`p_U-`D#@VQv{{KjpxH)GX_)2bWm-OW}VJg)|OATbz4teB8lZ(Cb26SLD_yQzW8ZhEWz+dQS)t3TrA>bbT0zP48Hy{&qvy`V_4'
    'FPD^<Dc{iQU-j$)Fir?6-0FHjLXf6O1IXFE&-|G`;WNK{YK8p!=a2vR^q247e*R_0a~T8N8Xs2Xw&q?kR{VJ669)L_Z{I)u^zCQ('
    'H-7Nt`%l09^84pcJNlS{52ghjpPj@#%c<P+4aT3kW1Gq2_dL~bJvK^<8E+N**H8cVx9`7v{Q2`v!5f&_E03LF^e)ddMqa~fuVa7y'
    '`0d;0Pk;US)91f@|N8CYw?Dq_dAd|LJ^b@u|Mva!&q&4Rk3ao8{%g;}HKW%&yyf`&@1S5k9sm8eKfe6>@$;UCTS=42?TIs9FQf&`'
    '?xWv4`iyD~+Fnk^62`?xk4Ql(5ZwRx{A~|0hNLZ&lkPi!)J-gf9ctqc+tHVe*gh$*4NC+a1AQ%;Di+aZ!bt8pr_LUdtiZrdp?PWe'
    'q_SB#Q<vR|Ige|+U=^}^?*)r-O^i^tOy@5jfBs9f42mDhEw?Ob6kJ!N5mu0Ws}-&m-(U^{3Ew__|LNa8ef+kA1|@m2Vqz1krCGeP'
    'aQyTI9{b0aPdlEhjn!iWjnz?(d9qDfZucx>slez>c741GSL>dDmYyAC7$Op#!=7fx2moszB@F?BvqwGIP%$&;Sl}@NK!=$Rmpzq9'
    '*(L08caQ|Yc}||}4|_7_3D3R0VOh>LOwjh!d${a5Rboc_Vu!$()Yf(hd^jC~uyKN+m&*psokv2*@$|#ykq13kayzH?SP?e<tqu~s'
    'q-^XUVk6FjB%nB-nSEGHw++-CBmhMd54qPpEC(ES0wm^w96*Prip{7ZmNagsqB{l?uyMqULhz1`zEkVt>ClN==fz=|U|3R;3_Bek'
    '^yJLY?|H_8;ZYaGLAq#3Qsb+a0G3&g+csVA=SR~4WF(Or?5KUzNLVqpO#9@K$3NKu0E!u&NoSY!UBw?SdplMEtXg-J04$x6Jhsv4'
    '(|8WyAN=mbCaDh-05gdO^r9CX0`~<3A1(o&n8&?yCZzD9-35^`ONn(U)wqAaFxj@<MG!3RG=;c7<>RgZT(PieD6-wZqL)(bb<0hh'
    'FGnqwj$G_}6$g7#q3_?LK<R@x$F})lhMDCm2}JaoFMErqK1lxrS2F^Ltzn}g9%G1DOje(n2d2|p8u6L-YHa#{-a1dNofY|Be4n7u'
    '&z5{vjAu_iTkbo1R_D_Ce%~;9*UThvamGM~otzJvNm8e^ZIdS8;N;geZVJ+-7EXE=cqOn%dYDuvwmJ<)3y%d1yyDbyywVEmt0RKZ'
    '$dfdQe^9kqw+Bd5iNreY#}OMGL=VXv<00Vz!Msyz+RCDQV23Pby%mrz9P)by<bhp7li+AS;MfVHja0O4-ybjbbo3=P2kD(9$$Hp7'
    'nRL-Qe1C`lY`W2Dnq&OZ*hH4{nJ1GjPKfUxF9D=OnQ^Sf)`v+TbwvAMxx_Ucb7HM7%K$9QQtP{^jJg?R`Ej*oyq$m7t<6e2$+AUR'
    'isU$XKZ>Laed7B=w24tWGo}~24iDf@?YfOIH@8`7qdq!`^)=Rn#46j+1SQ^um4>6Cw3yiw5$$=|m<T7pWNy>#G0CnhbG2|3ETh|V'
    '_g%V@C|a9%QdKx6l#0<xomSuKHkbsBxs$#<OVFKY2&$UmV0VrsW+O@weJI;{Q@0HFs2ko34!1~m_4?svoxOtZ55ZSql%AQ<BY@Sj'
    'j`N-wuXm0EO$T^9?_bdQ#X(R>LAZXOvCXS)PxI{(+y+dJdQ?7WW<Aq#k;2YwS>k+)XVl~=$x=xwK%<$30j4+&EjFk*<EwPxxE&eB'
    'OT>}Lu)gFShZ~9{8FBr#`1<+5dzxgU9=k8NMk|}_@$|5~>3poib|JJZ>HHXS_UQckaWXVdGN$_^i@9<p5>FM`PRoaLEmvvy!f=fG'
    'H*Ov^eSaDbk`yy}B=K;vY)cKa$Am5jw*(;cDgfzQgZItF`<C&eHs$YFyhhAeB4hZNHLceyl@mO+L=Ffrj$4_-+-Q@o7X4y88g8@T'
    'N$p##Z?u`lOZIDeQ#N&J`vfgK>xnf|VreWA&rIU!(6(;Ga<t+~@mGAikmLKcjI5Azd5|MrujX|9rX{>^!Cun)@j^Zo{5@BgC+R&U'
    '(ux`AW8DT2zCR+Ql<vaxCdC#EZkrtRHW*B*fr!EI$km}YL?)lph0odi=dYtyX{uwNW*V2M=5h{Sv~`la=J!O=MsB01d#@-;8JW!_'
    '9!(WHpR{zvLUyCoFka4H(rTbgDm9bRD+Jbc!#WhPv?p!zzp%1fSL}0QqDkFWh3M-(-El{RlKN$B3d+-J-#yT5?nLYXq8n$y7>;s5'
    'yO)>+oF|5zIBXY^3Zl$hO8L$fMjJ+Aq5oWSyVH7)lG;%r>xprFn%39tk*=$Qw!G}@M#4J;_(zC$<g&Ac;m1u#Ns^3<enPS?&s!X{'
    'PfWompF8of<?-#BzE@7xMUQVZiC2|}-Z$9QL&0%MqLR$N;VjCG?6Hczws+0SsZEq5^WERj{cX&Gzpcglfl4eBJ2pycA`V&)v3%~#'
    'pl+K(I|ltmAG#m<e29Bhn0y`<K3`Oo$4=B<5s#awCM{tyoZ6YI)Ni|96hY&{Ywx-1QnIP_ejN#I#|a>oAC-ShVT{ZSSkUfFAih6j'
    't+s#yGg>x|E11IQ?3@<TyP9}waoN|1ELf9lvi1tey8=4+{s^^TBz3T1Q8;K~Fk;3t(yODKN<iDRvSPo#eKF_zGM}RDHB@LDmHi6O'
    'fmbh^JiwCDL|Pwn>>sPp@TBlTug9V*N`mhXnNQ5j9eo`eXtOB0PxtI?=sMQGm)xFUJgvxPxoppfaHnNWnFlM;Vg)|GQ#1ee@t56g'
    '7?B*yXP{2>$FkKi?mFW-iQ`!{l8UFyfOB!AR76syp~ngyTB+dsL!=^XQb)<skyI+|%YCe_NS)-@_Nt3&+ZqOvQdTS$B%-BZzhG2)'
    'cF>VQFiJYglsQr?N~QbQ^=OoA93_1uIht!bGnH@}#Zgj+jgn5z!r5vh7ZZ_A9Vr)+dOQ6|?^!Q`#`iX6dtiGU8;h=E9PqA5H}J@~'
    'lGSF}zkRoUEi;0TBSJQe#$QKFKXhIglhi)x!4!cs&I@|jys*hp{~o*$xY~`m;|S47snj015VfL6>Z2&(B&`_OV+G<wq@+5I5>026'
    '78N!U5)LDT(j*<X$E%UO?u(-$`|xaUgd{s|+@o5KUSpJd$;b&<_F4VSwyK3}lVkgie>!&fh@G)y+kc~N!n*g=+}1XP+jhoo6T9(G'
    'TU<Cz%hY2*o?&rO(datTxZsQ?*#Lbx4-vboblZm5H4Z!fG<q_@1ZEM|ZEwT-<=@l|<&V{XCz=<W*`&U2uK_sv5vlEANX>OpZ@ZuN'
    'o7u&;zyiH3&N2pvJy>k~d%<EZ#7uP=;k(nFZL7`LUb1aIG@nut&owmnEfheS7fy@gg2}l;EP2{n%)-GSVr*4E5k86PPuuBn*PKN5'
    '(!w`lZW+Q1cE5H4x^S7g!|vH=Njmfd^vVKz9428)zL_E#A|A|+9p%ticR;4WL6|Vn4vWB!xJ<=-wzijapGr!*yRdjH3-8$;(+Uff'
    'qzVVq`xibN#HE-!fHz6g6<x2ui6kbqII+koc9iz9?;^iR^7SiAUXf&jw_l@2iJkK)L&a<O?RYg_tB+6UT(&-r!z^jInMvpbl%laW'
    'Hjn+O<60gEp#rp#vA^~FSpyk6t;gPzaD`ngx>Y(us+XQ2X`!9om>SIxQ*y>&-PpQA+B197EZHy<kDDdRCP$;(c&ARraKw>YQm_Ka'
    'nZ&NxV^%~^;oU)2R1rNF2E5o3tqP&NA!Bdac-CJi9!0I%qB1wl;PA>bSSRS&>jmmWjP)P3>A;PUX2$l!L$+bvH7K%8ZwHaFm3gRZ'
    'aFbPi9K;xwR*LA-@^DDvl*W?^Rc!X$#+B$aZiG`_;hA-LSC?A9vP*4A(#@;)4{!<Ib<A(kf4IZUsh>1+Ha(x?W`|AciHi%mVFUz6'
    '$<2<^RaWdBMyz_yh%MRQ2ac0YLm-`L5^FuIWFhV`UG6YE;Ykx}r_puTu;IxfJ+t_X0*mv*wqtR+gBzls<c6#)s|OB|N;=FrHgZ8k'
    'Ot(4G1%W3fi4=X-GpMs{yV0~3R2OoN=W$hCB<|vR%-eO-->q39sF8eTv~i@PW5JGcECf?Y-&ySbIpkt;$`0L!7mO#lm_t5ug?3nk'
    'P>F$pXr1APfSlqG7C1xwyr+q5><jP23(k`c8vRt?ETOa)3U02xdjW)(%s&#`$Qk8F;k&g(ddK9reH6x1;ZWOZaatcYK0>BvKRT#H'
    'n2aea<}lC}N&7iBK7_(zYWAVFf=o~P_2(@liPoaTWX1Tu=%vMtpIDB8PQ$^M-`_RBL0&k(0Wh2tOtXHpeuFw5nxrjcn%37VrtCV^'
    'xWkT^fUl+Oj82Y<$(z~q+nqXlhh>dCYx8AowjBqm%A|RKo&KVtL{RmIsf<o*-{1^_uWBlY#SVUZX3*Df-~aaW-#>l%{`DJ3=Ia%-'
    '=;S2vaLlk%Hd%Ge#xSnZTvq-V(BqRW**<-QkstPT%M>bx^IZF`nh=KOog^vewE^>xxx@9)sAP81u3r%L?b&gJ@*b2V9l)25-I~h*'
    '<a4e(bPnxWB1ZPaRg=QX#IS&I=aldoPZAtGCqVa;DbdwC#&$KwP6>$(K~kYGVtM@xk(i`<RHQ`nI)uY1p-K8O?GM7sT?gUsLI`I('
    '(^&8nYfrEQ!@)vfj3&jsIIUug2hdXlM9)Teb(ohRnURU1WxGKVhYu1{N%yW=41!StmX$^xDHfhqxwqpT01|fqjw}}-!ADBaMR#ST'
    '%&vMT_ZTH^lQcRfE-tQUz{RzPibW^KqH#`liH!7Mu?VYkfZ+%*fgcVqQdyPL!f<&G`fyqlOA4~}V24151BLG?Kf<Au;65hpYZ=u&'
    '?8<->x)!i79j3W>Y<LFjL|6X<-yb9x&69(+J<=h{MW6q$-7l%L=z}`_>>tF>mWCx2_?K%Ioi61ox|GtUIWfIeffhxKRg1$w$Qqiu'
    '3av?j2WpNrDHKWP1g_x`kn7_qN&7^1OQ-A>aeRNwTBRtFxgUq6G{MXgN1HZaPiQ$;Q0#=IS6{6ZwW)LHE~}Ml)5DHT)KM(6;1)~U'
    'or~uyE}n{~sCZ>@;d@{rGfA;WI|>dc%wIdQ@TB5~B*f^^ENv4r4kbsVtyg-`P+gWGzCXsqQ82v|xNu>R3q`na!d1t~MUu2;yBrM@'
    'iRg9cFyX0-xpJ5%V7~maE@fIcuNkeQO$3Z1^LLa=0#-eisy@N(FqcRvlN<=@fmC&gMEL$7N^~+nOQmX0Gv_7E9Gz?rq3?%f-#r%g'
    'INJ9!a%KTleU=owKWIJ}CTEsT)rW57VH49PW%=XS5X_S~e*0Tl$@vV5%Py3J?~f8n(j?%@9tC$0i6$(`2)ME${aq-LNo~iWzW0gK'
    'uWnswVvNaScLDKR9**A{+zL5YPW@EFmsdlY^dnksFmM`?uV_SSMw4ShSGFO!2L>^d1R9oGI-HvLlA6d_a>8L~>2Qwm%dbH^3+*g+'
    '^EjveOHO^klddI0!TocLUw-O~w7=D2tA%sszvRr9O3c=_JjeLuXTD;|A?W3@rsvdu$*HeQvj0ESlsd=w<)=Ov{IaN=*g5rIa_Z}('
    'G4N2;>m1^jpZP{`QBctBocAv|?=6`x4Rwz3%TN6I+Dp@-VCT$##hGsiOR7N(g}}}+e)XAeh@qyS2HZLEUvlEZU$au9X}3yFcbfN5'
    '!{8q)Rn#^n%8I0Jp-G#SiaiGlh^J>ErUky9A|k<(qlJ0l9MaV-JV-{uNVZb$X^cgONk}SASE|+=tVN13y;%F{DH^2Hc7S=kn1kh`'
    'l@W^-sh%RA^h85mH|AjRSh`Z1>M7!}%Cfl{RlTLsb@UKz^Cmkf2~4xUr@{Jm4OUB%8kfuU$P95dvsh0(c!xHsB|7PBJrr6yNA(3~'
    'H%)Vmma6KVllw&`H%se~+H;%vhneb3rj5lGYgV4Ir<a`i>1LBSC;pEz@nQH(K~2_k+P~zqhd*+qV%@R93@Z#5E0u7c5zequBwI3h'
    'CB1_sBw@a;)aQMQgjCYdysz-rcNf#V1&rAD3%kl;&scL#`uDqHXkv?sA%k1ktr@2-y!(YhCt0X@nYe>d&@j4E$@3{7XiVBt(47|a'
    'kAjD`te)p-LBAw0TAda+J6-1=Wa49^NnTK}^qluEIPYT*XE|3P_8jAvpZApMvf{w!)PKpTPi>O2H55VaHbGg_j+fvH+$QvM8ICvA'
    'j1g?i%LteZCU!t4-~&^owTyk=u|2WSJmr&9V$QLCFVMh*qDA$w4e>pNr`r5D(7}^dd_%qRb9H!mWZ+WCqEhvz(eRQpU#Mi~W+)JU'
    'j`7P+eM!q&1DrGeC1<`gWUZF>p?fDZ_Ssn}h5v-j6QIc?CE)WK;|EJ9Z4{B$qkoEkv`LPd<&|d-7Ldu4M$&5BPmz#GQ%5RZsako9'
    'Sm-fY2ksG9jYVjzR1;mTP<w%Yi>rtK<<A`={P~a1|GtAbW|L!!J#9T*L{sjya%!){fSxa(e*e6qaxf-z^BGcl(Hu$&tb%HWmVS7S'
    'rG@J`_32gQSXz?kq6k6S%HkY1jV3YI;^7)ABx7QRh@OBW<sqa=c36EQIcw?$p)aWR1cB(HANVQ$ZE70BE48E%C{;(O=<F)d8(OOU'
    'UUV@SPiervj?(yxigovs?fo2Ue_!$TbKOC&=<eU0M+Q5ty<T({8m-&=Hmdy#m$!eb#M~Qf6xsb%-Tj1Zf8V2PAMN3;3n8)gdBL^6'
    'v!SKWH0|fMY3Y8v;wY0SPCr=vKpm<$I_<U7)6y%;v9#D(CGHjWP+HQ?KRqe^oH>>hnH(n@#L~^%V`)hnP!j6UdJx0_3aDMP=a=99'
    '{^|R-pTTYT`tLvg{`;rD>><M@Er@!F^aysSM6Bj|ZUX7!X_17pq=i@a3RP`AtX9Qi(+<l&e*NhhUrvH^FgJ~d_2fv2P@0U+MPH-4'
    'JM-#gr76%`c@?y+i1yqxAr`Etf)kY!o4z!g@veo}Tq)kTy3uv0!kSC6JZJvx)5kC0{`~3Vw_S3O$)3w#AE@IoL{h8gmOo*ipdU=8'
    'g$f4!Xxuepb0wb1WZL!u=?$$z1;Xd1Zg1)xONml5r1aM2v7}f#x8C#?@1eA$1$BlIVo#XJLee?0^oIYjwCGuN>79>5X_17^8Eis5'
    'gBGUe#;A9~j-^GBIa8^31dpY~%&AN7iylgfqH{}g?+zbJ3ZIio?~xx%iXwB1VjmSamKI~@6qi54qSaK*Sx=fggBI|A=H${mgBGRc'
    'Ja+jMTI_7}Ks^I=4b`*$seQscGJ?%6jO-b5QF@LR&7VPwos~-;xjd8>3vXv=>7%E|(jwTL?)DMfV`)*d^Qey^A4|(TzVwmoBWY2D'
    '&Kj6~H2qjwvTCF2@vo)kqiOVO&+{os{KP(Hl*f{)ev`ZnBk`@6QXens<45KE+!QoYGz*UOFntN4;lC*UYfpFSFaP-d`{$4U`1Ixb'
    'uOEN;v}XrfF~;Q_MI)Mks5wcF1Ao~!qrY@qY)cqSELK5D&Efxq)~f05L^qy9x1R)F;=+?uga6u<elwQmH8ESwM6w$8r0yKnFP}bs'
    '{v}dT{%m24;B4mE1gi)0nCtD8#cVDuIQ}1lam0*nHvOjkyijy4wb!Ps31hjMTM-EHq^er<<6Qzf?_#~iwcM%BDixg)sP6kpv<U9I'
    ')wb#aZ+&ezxV+tq?JNV;-QUsn^V+n3wd?kDI}fGLg45me1nc%nMVb^R_Ky3Nd!Q2Q9n6ISs>4?ei6``Dy*q!n^(8?nv({IyKgZHy'
    'W`n`K4j)Pjn~jmE<_Th9Le33QKb4QAMawzWRnJftPUpnZBigZ~fVDoip~9X(iy(3?MpDsd(86c;%{6<1y1*=&-D)CFSOJ8c-Bc0o'
    '338E)%*6uKGgc!h^}=@G@na;->?++`JcrT(rsteodaLVLS|p#<m+A@nqRecjk}^-AMXTk^kJ%)RAZvGz%#Xb}1AqPa`SbVBAAkMJ'
    'F7AYwTW$3-j1a@<Y`zaWJW2<&7&;s67Eh3iC1#cu@(fzU?5ZN@GiXs}Y=tb%H!2u2=sI`vvY&rDqF&cbElQ?2bp4(HZMXx!&=aTQ'
    'krHl(kdEno$CP%Swnx@Q2Qu*2*W3!hoYJ&n#Czp=BZU#f1x=~9T981svj#rzGNkc3Ut7#$W-yT&tS!ysodbMB<;7o*Pm<lvMNA?F'
    '>;wE~AqBb?`dsJP4qWtk-S9p;35I9zDC?}C{%;?jVVBeNyn94^K;5Nk*O!#-A!{4&>lBOp^?&D1pd}~KX!bpfLhvvOV9&RsFp3y;'
    'fBRHW*$xE>#)o`NK+3EQzk>R4!90@!M@9wkaW&k#`#fM<DEQns5%6<wSisK-q6+>Vl)!k;RMWuN3dRMu_&JD9z&{p0@A<KHKLYLh'
    'rQcf*^v0t(+C+LeEVtEImqOj^Qr$>ntY^J0iB(;yj0;r<k-n4ARHyukPT_dOtNStOb*k}fqElo=r^Z7)I<T4R6mMTmOEGU?cC}|2'
    'y1&=x6mgUTDiX?pe#r(dtGbpXTz+4fU@6X5FM(CBDh|M;z|Hki*Z_J#H8(yUQ*~`o&;G8gdn&$fPl!~CJJ0~p%8SiV-N0*@X+Rf#'
    'QhbE%kKh0D@mqf`vls)lRyu8~JO)972QO4d4tEOSqyfx~TN<Es-I<H@b3)Xdq13Bn4~jhm_HeoH_$r%$#ePBzK-{T(|9w9h`YAMj'
    '9Jc-3Fu}&3iwl^<=Xuk9U-gvx_7nvd?ceJ1x4n;U-#6X$eLp-tqSMzNUVNl}uqIyQA{$WMF>sG*A0`*cCR@L)Gy}j-c+qy5`C(68'
    'U)kn`@vEPhEZ0k~`DJ{%oaf8>EoBGH%zfAXzR7XCQ~8A_(9fNYh837SoMd>Of3u*iJ)-xfNpFbsM$6dL*nag0J2pyw2t*&5O?wc1'
    '&ir{2qLUNRcO&{eDtIi;q-8|Ujp<(7#@ciu`g=umbV5A1kltYV9AdC%^(g4M;KcM!PVW3%UUG~y8c}O-Ylcr#_h#>l73$Z-5&}0#'
    'Z7wl|0j_IZD6M&tOOJ``ysjx}{bN##rXtR(h6y9N=bSo=%S8~amw(YfXF5fs{W<u?;FT41N;2@uIs6N*EcOb2`}O-Tzy134+ovxv'
    'O16V3W0U<L^qI#zRgI-cnX!t4CULDBYa8H6<~;eja|ruSxoz-D)>ubtjDa--uLM8b>?+!FJ#Us+op+6)*fpk#4HL@8YjCg39Dp><'
    '#r!B7$tBgifmg~+s+`R5dI;Wt^`bn6WGzTVQn238L#M#3%9%A)x0Vc_Y8ivMp4S|$m>^^fmZ>I&GL9HXYDr$42=%ld$#N~d7`1cZ'
    'i_1vTz54rr5e2o>$%qOy9#P4tjOvRPedD?EOgpfCgU*=_b*G(lDAN&@)Cg{1CE@U;!Yhv$NoEO4M^Z;c9o&#|MI9E5YR;Wa#&Vwu'
    'KVU4m$d(RKkH?atn*$?4Yg|z<Y+Y3j1Jx#H8sJ5aB>?&fYcZ%P_d0;M>L5H`dBj+9BeK3_I;!X}mgOos7%w#u>j+z@ybl;dk@q0e'
    'aS#V?%Lj4bs~^loZVQL^5!~9OL1G_~+?hW7)0a;lzy0xL$CIrjS?W&r<b0E>F!jHupe1Mz9n>U6!v<S;VuA0J$*8d69&*4wnWHA#'
    'kSLT&Uf^>NA%dox;NAELqZ-YzP`99MnNHPcR^*7eGVh@>(riV!@9TXQqiCvS`*Y7VwwFtDE;_NA))K?$lZs+v5gSbZ&o!}MBjkBs'
    'O$@>>2@)R>3fOg+Vi=xl28Jpt=4M_8-Mud?JPKanvWI1Ag_7`2VF6n$3ZqFsN_?%0B0PLn-d@HShM!4Rv<et3o7V+WPR)3<#vE75'
    '7*v2Wn+8dO86~U0_|^v93r;O}(lfA~Ja)SXHaGl~?BcoIrxk_k;YvfjbC{rl2~lWE@|~J~t)XX#Vc;BPc5P(u;*k}z*S`if7d^6_'
    'jNjY71-3EOCK*$jcw}|cXf)=%)0J_a0ZZI@V7khgraTSiao0qr$5fh|$}<t_##IM+WQH1qm250&;-i$aHT;`z#k>j`zWW$blcux)'
    'L?jtY!FBKJ_I>dHeEjz9<4^yN)tJAOTj*9ANqIh#kfzZVE6y#TN(`SA%IIo}Y;vA4mq;$Lhf7G4Bu{iIkEzTaEFmyWQy7R(A7H>p'
    'XK>S7GiHhL+^ebqzn?Xvn=d?<X`hWz*(}DdT+BJt9;|caxwe(YJ3Sm0kV&oRs$y=kndHopF?$&-7(((0&Sa1aMR9Myu+oyWFjJ5j'
    'VyI&g!xAg=XeiQ@A%;2*F)ZUr?T1_<xx^kWA)cJfoQh*AvIh%Dqy>_|7L;SaU=o&8(CsQ{PnqY8DTe{OhIccG-t5)fp#Q?yy!-=B'
    '*pvx)hv3lTndql>`$`Kc82nmnIVn4}r0az6soSaD!yx=$Iyi2`36ad|m|cyb41o#GvT_Cnr{5>y`HDE8d7qcmVW3rQdaGgrcNVyE'
    '7_Wglg+@m=#R_xOpsMK<NhZXmN*1Q6H2dAJTewR1GtnhUpt?F3s<jlWmdmDYO_xwMzt_<(p)6TK(*^rV{d>STX=B&j$M{Kg;1Xt}'
    'NEZ1_Q*upuxaOF=^H3&^smLBIAS;Mo31?7NJM_)HtsMIMjdl!u^G3aeCCpkgzk-=$1*_iY3Z`J@8ofH7Hizd8!nwk_N{J_`GdQ=0'
    '!a0bFO;AfuP|F^MS}L#mkqaaj*uw?H(?S7Lc}!*YU<nCovM8(`!xnMy4?JAQ6tTfG!KIAzLJzLGop;rh&RliM;xWA@R$YSMGHzUR'
    'gsZNwRZoh|B=DLF7g}5!zatpIktKPR#e{$T{nO{q`$tA<wK1Ev#%5w14P#OkUr02waQq&Caw;i-RXBKUZMn-<2liR#@%&WR@9uKV'
    'MOHh9^l!iIVnb@0@=+&z)NfG<HBoXu(aXZGpCo*pHf#XOeZq%-lft)lKh4Xs_fL|&5hBx}D&eDgi?TN+F^LO_UKW1!B;i{wGd@hh'
    'hk1*_x8OhQCwf`<<~hQrBu#T@uw&+!5A_CxPXR0CexjF!ubw1)%9F+jw3~swZOgjW$wxUylnIe<(;-c%cf{JG6o=UUl(VFmZ7z{q'
    'Vh@*)pgIo+rt+A|?7<QeMy46&@#%wi#2c<LY9L*so$$;nty~QjxP5+5N71z4*(Inm=Aq#z;ddF-p^B^Z3AH&qZ!xGtm8N5zqb8k&'
    ')E$gldXk|}O%7Ys9SB?SW~|t`KyraSTtG%og7v99rZRi5glwAD4pTlkwibemC%Y_6h=zGqSAyVakH)<P*s@x$>f0vuZ*f*LqRsp!'
    '@px$9oqMNf%qUH|nF^K8LLrZZEyfsIJw_Ejk;lOnV@VcaE{|MZ50?*5BO+6AOhxu!0dXr<PG<VLJ@)1#zV*B!jKyhRy#dey+g{Ah'
    '?lBMWPQKUKjSXN|r_<)}yh&7+DoM;5joWCXGEG!#;}$FMsJAn2Dy=!&U`3vhGe3U!W+D(wX~Opty%>SO-#;S)!BRuM;oy&q*ciWi'
    'JF?d*+odQXdQtYgd6Mi6W$9|dlZ^}h7I#}%mSj^%^s?~lX9?dX*>jSnwv8kQ+k#e^tkQ)>no?sBsXEFS<Y`-<Tp+o?9xWhFCh0M$'
    'G^P@JuzV;}>GX|HA7xXiXl-y=V;MM3!FG+-M)L-YL7;}NYTG9DZ_!rbOef78F1FHmXy6@rr#3F<NlE+>e`IV6CW>g*_>1Su%^TuR'
    'r|DTp)j(D@aJ)+$5v?|&KC-BkIW&nOzr+}1wzhiV2y!O6<tJod$k<3@%v$lr%)wfGLhftx9Xuqi!15C^@1BWr9+D8y;uG>H=bmv$'
    'qJeyzB$PZMi>sE<o@^#8(_Y;`dsRYvzLix%JEl8LXrJ6UPZ=zsIZ3HozVkGZZky(6hUSU9^W^M3`krJlFVkLKLAx)ybA82~RgqNW'
    '4N{Rsw5uy<cO_alJyEkwb8-fAnP#_-<_Fi<hh<BoO{B)lR;;nlFByxe(aOfvH2F9olEo4~9q%LfX<vg7r*1+g=DF`mpT;uVZV>F$'
    '=<Y;MW@6Q)Pva}RW%2NYxAePW-o!F*S#UYwE!{4=$GBx%lnHO?cZ{w*%?wW)^O9}vCA_2=3wPnATH&R-m6t5TBH<;?04~1!i1sXF'
    'IiWrM?i$*&-1(ID<T%hh=1X=0E9J%9%uBVxi@*8q^~&AV-6bVgBqeX=MXm7SZq?YVxI{vG`rTEuyE)n)T4UKN!_v;pqw`%OODVHz'
    '<eF>iV%MWL<Jwwb7S69#34i9j@+UP(w-OR(g}A`u!BuT)kBLsoH31Wyu(Ek~N=MHh!L}qlf?ZLnVm}HithHE{NNH@cg-Nvd!$x_n'
    'kEl-!Oe;>s>S3u(wkHQ*EZK89I9;Hw6wUo3aTctzOx>B8xZkO(Ovy$h?h*-l1M039rt>&7l7%teQzXtBN%KhDrDpA1eCBdKYZT*P'
    'nUP%-E$Q!Ml1R^j*<KV6n59h?+{qW+i5J{S-h-xxd$JbMXJOb4slpg~QXhqySxckSWVh^7&iDvh_gYbg>8a^0y5#D;{H}ZP)qBZ%'
    '(Dhh5OasQs1v|wicFH(jsMmlkHgwW&1=x(yM$YHcj9JR9myE%5#eNbaMy0(Gl1;g}Sn*{ky&w*bh#-4o!`GnTqp`~v3qHhxK)`ws'
    '%jbp@t(?q7Lr21ym|WLl!ei&Lv0~w5#W;AI1zg`t))@N$%vjDQ+E3Ra$+J2uo~W}e8)>1&MDGYw%Y}e8^-dhFcgPS7OUe)k+Dt}d'
    'ZVzEe@nR!CzNmQgISNQED34fCz&Qq|W-TA(7OcVWqZN@_N|Q{$HAPGVL|cl;#e5L%v5H8oWZAJeIqq+zj1GA2s*=o8>bVqNU~M$q'
    '+Ry6Y`n2&%;3if@77jP$Jg-%#4rsgrJTU_kBTI;nZ1wGsb})5;^^Ha(h3wupgb<l!TCNmmb+wD3j^IESHPF>mH5NjHHHtqqy$WcT'
    'mRqY<3$JdH|JL%WB3n|fR^q8OtU6enj?>1%r&xJ07WX!9VNCEe=4!E;P4eI5nCLWRDz9h0RHPgHvJ4Y&hL59>T=_bd437uiJY#k6'
    'SlE!LVB$J$nLcLhEEZv0uWw$?=3rO!>@GkbyH)^qA7g8+U}K|-t9FbY+mnfXpj<JX2)=*v#{9i&Po_u*H%W>0o(`DRjmF*@nh~L5'
    'w+*Q|;;4XsDZ0>yXsOG_MyJsb$Y!T@cT?+|yw~YLeTY!RV8)rbp&s=ivU7ciiiY4yfzJ&X3U)jYd9R_h0Z@Y6^g5*XP&*iw(3OJ5'
    'wYRY+I~9%+={c6ULTEz3fAUI8u^c5&YuV8-w!NvK4VskBDpfPjuz?Pml$1`eI&|%Z`@U8VR%kRvt4d*~z5dGn2S+f+)01CQhiG$b'
    '-kuo&YzfZuPOCU-y=$>!%r1dnySBd4y`%X6rlr;^Th?F?)^Q+p?H%x3VV~dtJhSIdGEl;_3Cc98xk>&T)I&`qPfIDXF>-(<#A82K'
    'i4~wcXI@v>WtmQ_Jgx~#y!K$Dt`SDTmV_&ft`BH^%RX>$?`(3`26X%~ugW<ZLM(c2+!B|)jMsY)9&kD-!%xApMY!mEk=k^{Zfa?)'
    'X92umY{yHRoLOu<H3oiRR2AVzDQB>eZ^hcghNC8&!0ZE>pU^}0fKt)<AjRwrv9O-aMU33Z_`Syz*k&dv!cgpUeE9@s(ARI@fBN*x'
    'r*CKveg64tc>oV<4Dq~may3?_K${vn<m!rw#(1W!c8&_h*aQnK@ndD`yA#*4G6B#YKCki0!<0!Wnr*XV@^LlRrE=~DT<E!6)TNz#'
    '-&>b}YnGmwr*<5v(4l5Xo-&QCaG0es4m@9`a+WKbcGDBJ_t8-g4aLgnUI5@(WUPr!z{3aBPzvkT1Rd-+LQ&3M{~Fj_Mu&Zj-+M%X'
    'ZB3J1kaW3TT8Nm=S@tAdu1T;l>Rhv6B?B8;U;z4n<=RrJc-pBxS+C1kx<uHw*6TuM?>&0JD)ukU&#jQP<Cb%qs6uDi)kViDXSZYB'
    'b|TgE_~hK3cmYk*W0Kd>RG17`awm5$i7%(sB{Z3Bnx+RPucfIlk)%LQg(-d|cdC~5Y4_?=VX|NeP4aGcQg`Fd-Rn+;sTuC6sTo)f'
    'k4(>^4>3n|LG{U@xUC)WeyU84rOX`J+f4IVO@&Mkv~BLxuhNwsx4Vt5ovEYi_j31>{k}9*X4dFR53Sus*Upr)d#1;(->ce{39`<k'
    'zaw4pj`vb`<k8*lUOUsl+!NBltdiL=kSs}R)<~J=sCMhavz7u4o-$v~(xYisd<r33nWcvegJ#@h{Vk+Ss_hbK+nsJ^edU>Cf@36}'
    'Rk>GV8L7uf0@g`^S2jfH8t$iQ?Oi-K7@`N-c&Wt^F%@eVB`Pl$8ri&*<t=7&IE>Y^yO<<!r2y{k%o)a1R!5QQalFhr*Hv_~p;DfS'
    'hH0mO`AMW%$}Z8jlSHk-KgHY%ud52g7T|l}`q9of|3E3Dl1>so^f*vf&Q|{#*jseS3mLxe7)EwEv+0gh4J+&=pdx9A5oXPt$7DPX'
    '|APw5NzN=Y>CUMaO&yyDnkHaspq0eLy*AO9143lLoS`~zy%)LbBP->+^{;`)#rW7xuJ1mehFZ$Ss~)ET1})V@@U=APw|{n|Wy45Q'
    'n*RLO&wn680GwG4hDg!^6>9|UFEH+Ppq|x1w6jf2kfiGNs5(X%r!kHlYN2ZjfUBr=;<AfCygvp}IHg)n+8T%?EwG%;0aU8>Ejf0r'
    '0PYPgz`nJbt>m~brEc>{I=Jy^BTV6qY;jX7ywZotACTh?Ofi^=`H}i0$Gx1X!Ikjy9VIVFRLJh#N04C`jI5EB8;>C2wn0^6jdfsG'
    'f>t%eHo&aQnZ@ka<iH!X8n2|%D7+Gc5cd=s=bA%ir({yfEKw?Q*AHYlZ^MxFJT9*HJGs91fCA52*~RU!rF|Yg^|DBI=ENF{S8^q+'
    '1O;{8sROpd_y+|Z5@l*}JFJ|gQF)846DMWN-h1${K?2PGWHz#-Ck@zL5henl4#!-KASC8@@QJHoEln()z_rIK8;7<VEJHP{GtmyM'
    '+ALMU`T{=YfD8owL1XfpopdtGDw375JB+QRWNmEut%A7sn1dLYSy@4s76#tTSV=sQM`I$RFfBZVi4hcaXe2y-WEplNURglPc^a8S'
    'd}9Z@jN7{pA5)BF3n)thTYyOl7X&c7oiUynkPhbJ3Z63y|0QN_gPtiaPr$r_`&lDGJWz76D@^tHDntB(r3%I=4}!2HuvO0H=-(S='
    '?v(<#_ZS2FW}#k#Ob!%}cRJroO>baNDKO#}j_R9)!Riecq(DYA;R}^DUZ9&}WRMc6X3w^-G)Q}IXWLsw4Sm&CQIS6;(&APnJ(b=|'
    'F}}zkCy5hHXA`lq1g|NkJd=S1C|PNA@P5Lk$e%TnatnHQzFa}!vBE63f?{ZenRmP(H*GP?ZM^L(3TtER$WbexZ8jh5y0S@SxmO!B'
    'Jvj6Ys+d&@8fl`5wPCMLO<Jvnwlkeb-Z9OIuciR)OD7U*_u82Pv`SZ&YO}9m)xH!Ket5wa)I&>Ow*WBkr<FBYylMqtWKe?}I^TV1'
    'x#sJ;sfijHq>S;sMPJ{MRRRnek)F_zVjN8|R>XoBP4EVDErOFV*FsE=uqfXZ>+RRO#>9r$CNMl4&5V*B14NCYE&H-Dh%!{v@$ciK'
    'Dq1rp)a?~+3rw)WRD5!`wD+^J?aXlVbgM1eGh%Fmlxz1;PQp{V9`C+U@9!Q=12GuFA5-9W)!f^eSxxSk!F(3@9V>v*S!uG8`nT^W'
    'xMMX{T&`s#*%G%*JlQR?nkmIgGm`8c`(8Z7z6a<rdT&MA_hSBv4+M{mT6ud#+GnnlEgRZArXcO{co+H6W*+WV>e0RzxC8zejMsVs'
    'rhD^IsK|y;>Ou8qkB7U+Q0nbZYG5tYK9ZAqN{vo)^FqyHp0p1XkN*!>KG<avAA~kma<Nt<s+g%kKlN5_ULm{pwUm)r3(%ogazmDK'
    '9^_=t-DkNW;9ABj!3i@|c+RUsvMa?038N&5SxF8lXKF}x-AoQCWcS`92+U3fFgXyjbjm}TNpcVEP62hF!tdL2MDV!E!2N0$V)5Q%'
    '3do2LZJ}VjdN8J(y&=zst{--ydl|p?kZP=!!Y8X;bJm%7^K~W)XnOHF6J>7aS!d!$sxu+5d9)S_fCfPAk}4BtWr+7u8N&VWl_B<p'
    'q|V9^KT>4~5pxWwU@H#tlHVsM$AfH0OA-j&K0trNQjTQ~LtvpjpVuDxZEAf)-vVIL2m?0xio;ya<Z#3yY!xK9lKp$z>cG4;bfw(m'
    'Qtd)HIXa|x>OTWa#RHg9YmGg1g)tRoyFYk9<p(0*A9A(IV>wsDCL-T*pbPoE?+8Y2C0i-(xNuBM`kd1s((wb&G}b&ejuE^PG}0e%'
    'nhiLTl4r;9liH5O91Zy!Vr%RQdA<ACNhyhDuUdIPexOzgq2&9nJP_HC-0)YaJb(--gtV0+;7b*))wFK2>(p%syXkg*N*l1gwr>=V'
    'hX-XiqRg-SAhcFl{Ap4Iyqvwuz!JR`cH71Hy}<<7Hp=pqx-?65R@9`-0<432ECJgzDsCA7Z&Z06J67=n)&j|JBTuaqq$y`=s4P^i'
    'k7O~s_Z~rDmI;#XM};tM-3Dw%wXHzcqywwbS9PU;*-2evETJ`?m9lYldjy;*3A0?%rmDnY!Ej*Cnyj*T#L6(n%5wIGv9w#o26i%j'
    '_c66bTV+-%<S*5GR}*^%R*wW}1Fo33cOYHW5D*vGoOos9s6J#&HKy@Q#xyOFU(ViWk=#Jqos8dmOo8q6;8X52Ex7`EQY1^+4svKe'
    'O?{MBg&u$98HPd*ahfbOlo`G1HI=h9cujV$ci0$e3mLxm5CXfLrxi2kP9XgD^Dm#ifBna=KVc7z@&`*TXtLqC@ZcqmlgDD~jy;ct'
    '$;i@2j}EDn`viY{`MB2;z=zwcJg4Z+^t%`kA*N6QS3X`T@v<k>WjrA!_McFHR}5ky&{sXV-ZE(HJb%jv*WVR?V9N1VJ+U4c)MVlC'
    '*bAIkZy8kc{H+{Ve^&#TcF`(2(EeV|#<l$EY4)?(otVS6Qw<86(i9x^eqTr9_j32(Bk@;p_YRK4M`gB*u?1zu?717x#Iv;x<(+Lr'
    '_#Kln-s<^!{-pEuH}Ux9&)cJt+q9#4PfsO+_mZ*VK96I!aaW&fAVP!LrgS+KOMT^28umP&XB+gaZHcv7b-=H!%L3PB|5nyzZDd*?'
    '@1?2^v<zCgx9Gt8+2(}rlwx{s(SdhlIfCIhU2FFr!!Ix#3p15Vj=aCCWBB8`MWbFd&)oLLQ8!XP<{Ub^<2iKx`sdJ>RN}Gbhr#lp'
    'Z0|XAlHuC3%U()6*Q}J-ecqhp6LYJe*rO+;)mqTP7FStrFIm&CODU?y>XS9p=I6`V=J|5BwoYOy<**0*+;viYAXFP*G2I$WI(l&B'
    '>$bU-qE>sx>fqxZ+O*WM=nT}pqX!;1z>U<pc9wc(Wr&r2o6y-obsz_nI*v?QC1}1?m~`|gXLI<sSZ|EZt`)$2w+@kgL;1Am1KWM1'
    'g%p?zt_YRL6HzG&#K;A47&5B8w?FBftS+GLjR72r!pepEcrQ@M0Qh6@@AqBCpk+cYCZ)c+G6u+y;oL0efG=e?>q&~75rmByYAVyj'
    'l*YQ&l6qblYY)f)2bQFvGV`d%N#Nxy4f9A4ww{Vo$n4$M6A7c2r4yxHz?NEB=}E~mSyMiqbCkoHXuYD|h5*Yj0jJn8%(Sc9wwIwj'
    '#n^O5S|2{H*f)yM^=@G0><(FgJ=+Uo%WoCLy~iBHz$sm6DYeuhNl(fGIFU9XBEiO5b~1>HI+z(Qcx>48@S%m#!~E5iUQ*>u4N*+7'
    ')rP2$-FpupFe|d9uwCit>dB4w67d5D!B=C#u5=?_YN@O3q%em|`z$%F<LN7g#ys)ZODy1IY%FW-fi7X5GHaS6JQ|^3(U+@DiOabi'
    '98<T|X6Z&b+*_wX3c~WmDpjD%yyA7G(SD2O9lhA79doKRouqHS3Z{x5^jV;o<p*EI&l)h4ky$ALf&rN;DK+NW_n*T&Zt!!>!K0R*'
    '2ckIU_!?Qq-z#HcV<hUp>WrU<*h5kT!>}gK(&ydoaHH9!EiJxZ`n~K1SOCP}_W*KDyOtoW0?Z0@eqmh!)1&4xb~|hc_dUN-I{{uV'
    '3&66l@N3#{UjPFV4Hhc9x!+4lYTlh&<HUHaD-tj7)XH2Wj^h#c;rcP@IKua1-g<vbn!yw|bMGrdgOR-H{|<gf=XC*HIveu%lVIBC'
    '^?!+R-r|tOOW}U9y+i*ubz~!b?cZ)9sTmZ+?;q?KNWt<(z=>lJ^k5ys%En`iI@GZslQexpwDj`@81I#$SEXKYdL`>sqwIxhmMc-O'
    'lKuC?o>}*Oua3PE&kf0NvX!;RCHl|BWje>_dDDJB9INo{CO#MK-|F(Wy^n6+H{JDZBX&f@3!Sil!i$fh-pq^)c!`VWSk1?@OOr`E'
    'dq1clBhP%X^!fcHWTVOT(l3$yEq(c$pKR7hnt<7GRSIgowv9pUGIRD4Gy=hbzi;8CR!r5mMCaD)p`jTmxZp|8@*cE`Gk5;SAD_Pb'
    '<NHrvK7IW5$Cq+zPAXw6$y-d07pFZGeEs(QZ$JONb0+@y+7h*g7Hbj%yO%<4!4zf^_0rf)hlFKhyue@i{5wcQf+@vjBmyo4Q;il1'
    '1g04S|5s5BE2e5xDAH$LruK8TSTeogWmG$jUAIu*b)qd>Z|UgnO<0S<1@Cok(wTOBMQ*e~;9?Q;hkx!AzTPQ;%$%KDIq>iOMSm6I'
    'rNDE|FesvvR*VyWWv^yT=iMG^tQC3%53d)~^)zYp92NujOA%>3IXf$xwEQq9ZG7Cqov`D#sf;-!a1VY5*tK>sa9_^S#nj&_K3vG`'
    'z2haoDz}WS^fg{;&Z{R)oUKj+_dYc7O3NL?S`vo&D(-bluj7sqC9TsIWW40@;|kA7F?HJCxSZYoHL$%HBfC)$cOP?D5o}%oo$f#P'
    'QcxK4ERuT`$$g_ma;v+Qkv)s#zDki?^}#AeG+n?(gHeBW^&zU&N}6ZI-JSP3EAH;1>#h}dt2<VsJuB|+y4RbpxQiGnEtO&|#cpn)'
    'TTTgm(o&!~I7g+4>Z$5&<#8S|44R9?%+D)4EtM@Y)3!2>RO2*m+PHvMYU4dN=kS#`*uN6KXfu(F)CYKU`U8<%OJP<kK9#dMY|ixT'
    'E~ar`DS-QWa*=&2X_|Hyz=ORMW@{9&#ABBoZ_u5U#MBisKdo)uv^fpEBxpn9l}ZTg?7~=RWThV-ebFD7l*~>tS&*$uLAG+X1~0v5'
    'Z!rQ>$nd?#5ZDzqpQlL~)1{i6W?H^F%cJA9iABGqt0i6;T<t1;z!-9jA&AxLrR7`=(frLsx<Y>MJ%qq56WXj)EnO<cY3fORM4#5Y'
    '3?{@H>q<0)TDY<T?13wR?IW^X^#?(fN{c_{)l18n8<s@BRq=8s+xH$(VA?X74ro0tVyZn524G<Tcvy`IC?Tf3*-7nPnUxl<jc|CS'
    'm0;_5&kbo@Oqi>x=76J5`hy}07RY?fjO-0-W;uI9gnP5J@J`0>J){cpgRd1aU8=}wC;9lmP_kAA+QfW5T~X1%(xI((c;(~AQYcB*'
    'YnPUDHL|%kmdZkY?>>Y=DZ}+j%K1_zwN*2n9+IM^ys^<rv?fRj+KJ5u57=zdAGB7I=bI8q%6U0c!%E4wN|qL~d+!khW_7;XG!CMZ'
    'z;*24*f`vo_N=Z6!xh|4swXo|X%a%jYT0ll(as7AI>{V}3(KU7=p;9xZqSi#l!|{JKCo74BG}3i%h{m+?t_tw!R)tn#4^f*QJPoh'
    'Wl2o1eE5fq!(I&*ci(PQjC)T36ob}$@vJHL<G4Z=<}5rPIvb{Y{@GGw-cY(wo^YjvEy<3YJi8bJFrqb4dDj!RS*rHEoSlgbQc2jW'
    'ma2^mW~KK4B{xge@-_ZqPB~xXk3Nl0BVM&)ZRC$j%Jx>QRcj3Tu?_qN7!+9``jtx7whU^!w`A>fO<>RGLkhz8mZqKBX>@(x<0++S'
    '#obbLZYoVXmXjDM@Ro&qbcx#T@Z<gxwaeP@B&!`<HkO9}MoJwCT`o~uxD7_0U6NMZF`MF^C27Uly`EQ+mNl#QQg6@gFld)86enG-'
    'zWQE@lOlt9!327N+N&*l#;8{<z8V>1!n|tj)yN-^ZqDMX>m^f{Gm@^&6_roSri{Zb2t8}BUYYGi@0sl;56=X{@i#{9uf6(STvzh}'
    'w_3PSduy`pc03+BPa_+Giqc|oc8{$njxQz``O)0W*DzeE(fVEtB7^1sgf?rnfD5zjpSeCnHl!iCQ1N!Az8(*F$dI8#y=v`D;EyXQ'
    '-*@fI$b^#0zDn&(WJnW{Wf1B#gRru(k}+I_>8iYT!D+$lBwcc-L)?98or`$_n59=K&qTvCCc0wA&H;_k%?I$}C{H)q(7w}YDq$&m'
    'gQkY9Y^9xy-*=Zdvdx)PD{ZuwdP3Vt{-p0WrD(rpUKzZSI@(BJjT%KN`S4U1^MMKQawkQ%)ArfrY+W{M2wzWjDP;KGV+iaDA?H_v'
    'mHLWrZDYfH5Cp9F#iJ05Cp>p=Y&;nEfekbZOHXv@H+G@}8L%`hZrE@sk}A86iK${H;DqtaDCx26tfTqtsbv=&8cMk9SeU*7f7eNv'
    'Bfer0@0vy*0`!7glXZ5+O#zWq)h%XkSbybQp{y~`?_~VmAkoJ77j3GcKxJCE^1(AjV$!#qO!y1nCM3>RAbIFakl26R@RdUoOGg3R'
    'B<&RqiSbMjMpbyFQ_2~bS)_vXgIzd#_)Ng_OJe=-L^*fEL@?`Tn&@7>?>!NKYbn;sNiU_Wx=9+W4rw778LWwQZv`x4aAm_9cR)F5'
    '^TC1vE&l)ZuBOLz9l8FOtb+!>iY%@l?gX=#N#@-*0cH_ANR$K&5X>gYa{ha&C`)ZgCPmq@{L!tAZ|hnzkBTCTtU9NR%H;NzgBp$z'
    'T+-bsguAx^z2MZo#q`?VLs#Tm4djK@K=#w{DBD{tY17eaAb6-6$XC+vpn=FrLsMvCAVRLvbSDvyZ{dwM5#HESEMr@^#O;@+v#an1'
    '9wxl;mBcc5umV7r70U=uFP1?toHQ0y>E23sy1f+wfL6>l(cAO&hv8CgOj!3)w=|o!EiJov^I=gvqi&^{$YpR9I9^#bShpf5=zJ^&'
    ')K$Gce#?6eUDw=yJ%Wll+l((7VGiq&a*)F@f=!EMTnB&m^$9A@WzE#JOciIW7DRR&=mDp*%*Tw&IL?*DpsWpwuN1Pu19s2+2Q9t0'
    'ymhvoWjVah0VdA`mRo`EYtsnZ&rCXvlBBl&tA(7WbW@Ysnq^>uwUt8fK?$s7%@QwGU=Vlb>H80IXuzV&MoY@!jsJFQCfx{pZ<7*i'
    'XN}A9^e?l|Yq1d1@Y5n0pk&-_X`n_P-ROK1>){-;wMXE9o++;I^-Ix>Q>M>Xot0a0?`~4i9L3G-?WMM?>cz%>E2evUp8V@xTURxF'
    'rA1Doy!+lBfkG|C{Pmpd?UjT2%t>C`+be{-y9H4z?{r2GC8h3BFI2X?or;OkoPm602o97B+9)TYF33shg~lRr$Q)`sy=*Ekj8YDB'
    '6rQqcVq#Z5fW2*OsAnlX^N(P%11~YM^Jz(f(gdw*nkuNd^)l)J(=-z8F-inUgLJ!~eWU8=0=A7i#I_(6{d>L>FX3z_z8u`Bd9#*8'
    'vJv*)76nP;Zf@93jVAR%$iBAIVV69ESl`srYMskq(y|Q?8Fro3=yIcOIi_(1W7kIALbQ9^kNhCvJzf?WNUJ5h3N6IblFWdX=b3o&'
    'VwhmILBGt9c_08Q0N+(5p$F*HW%7AOCgG(3IxR20Vi|damwLrqf;pE_M|hP?_=pc_+<#Yf1O^B+#^6?YgjeA{Mu4Ce(K@%Hns61N'
    '?{L+G0%~AcDnp5$Kw;WI0lFR466_vo33m-%^gYmFq6Z=mcxj1)o2Z2klstg_BoFd(02|}Q`Y_1@yNBe#9b;15FA=P??<!kB0KKuP'
    '1o_w3Er|G>wr;C#!3%kp-k^L}*@7OPdoJ06f;$}{TQIqkd<(e(HaA%9o?os&J*QlOk}oY+!1lLjt=r1xPv_!1z@0VXBc{Ci(o`J('
    'Txw0R{UE%1Q_%><Cyn#wwM8R(7zqAdR3joF;Q0LI?e?^4M3w7!oKZE_x_EfU)AV8qce`qYc-%DI!;qlueN-dF(eq9Z2!wxA)d<FC'
    'Kx&<<kCQ6*5@5mB^P)S?9>6FR&k2i-;NmkLgp7q^!s&Z;dq4(W4^m0xURoTZhoKQ6Q|_nSR-dD{=<+ELS6Xq`fNKxl7^UAt8Keg^'
    '6GEC70Zdi03kw1wqIBmAqS`ev^;3dXzT*2eUFFGU7Gqj(*UIjcNf`$z(Hgvefg=X(z*tb(qJZVF#}RdapXkJ9uLrVwr*=S3!(`-P'
    'Qd%crQFVjnsY&6Z#`P&~7+hV~LACV%)!n5;2$TenQ+<@BEKE79F`)<6DjyXB-rI%*R|_+>p^)dPJWh16VYRGSH$^*L$F!H=*W_TR'
    'Gsc9O25SUES2pT^;#CAn2}^E|$>b-c@@~RH*a!TyoD-d>qwRx}vgVp}owz^cy9Y(X#GGOw<Y$6Xxuwb#ZVGL<ceiA)AWSA3tK5R)'
    'JLuPHR~6d!4q(wLw^h#PMRvOhpphWGvs-0;Ht$j2*@Gn*JpPwDaocLFs|PF(36K+ZI!*$dJ8_kBf!_$lLx7;Om5AjUL%S$@r)De{'
    'Yx{ReD;Wa$K`q$6DB}^bKLpOwTc!M5?Igk*tx^teI7XOhmdiHadk-d-rU5BrM#?FrOVliQAa=GSZg>o3-T~H7vmZ)7#6F79O<$b4'
    '(cS&4a}!7>oLic9qUcnPay0GgV)9D-dz;urseuePEk(3y77J<ZgqjH2h!FG2=@JQTpk=ZSeC7Qu>QEb<<4~pufz4uJrNT6&T!+p@'
    'vym6innsFj#aA8y3Z%p=(XQN9<Lu!s>Gn-@ddjT0d%q;OPTDM0wA_m0Mt4|CqA#@X9pKVXJI|lo<cIwB$3Ok}{pa8Q{LAmZ{`gDr'
    '4|^Kp!RhrMP9dKB>|cNU{B6rmBkFkwP;SqJERcjL%+4&3sreRldSOu~x0_heGs;7S-P*LDsFU4Ivg!-TL-m8BpUr<~gCp|7;ZE{U'
    '8&ij?{Ze$lrKX-%YRc^>o%F1-Rbj_=?I|^7ca+omLb6qH5C!8FWrbr4skyYKxwvebH{h4KoBQ)W$i*-B?LB$+faQ&#XE2{gE;M1w'
    '&nwKVg;Oh@W)XmLmGBe3eBH#|DJxZjwDtn1O$;TTBmwTcCYB#O4_Y+YMPfO;;TU128S~qK@4HxxuyLCGFpsmPA}!4#dQ*i{q<m2D'
    '4qXg|(DYG(47#pDxIbl{KuM>xna4^eA*pguBh4ZR$S?N`;qGlg0=o!yPem*enhecS^FU7nr50T*O+gQ{lY~f^%5sv*-3_RvGT!I3'
    'D~d6Vng@C<q*#b{Z~GBeJD2pD28C1Mzh<e@CTBX}p%31>PN^sjQFs1;pfG__(s+ZJIB7YkF&{;)>VTKQ-Q9vpTAF$@+WaY{`F0_-'
    'qN}NnjH{iGof3S@Q%>ltX5D)M?ExA=1di5l9xyM?Uk>jx4!Nczvk~~-Hg&8ZHk}sLBmx=Q(}uCG6t@pmsM!~27yIMX8Pxf{Kx0Fk'
    'dnzGmB}(^$##R+a{j}(_rdS=4K1J=^Att67OSrj-)g&TW4)<)^E*lQew?2s7O-^2ep6nsd)5cP{Q0+3*BSkZPjV~AM+PnjFH8_+K'
    'l*^`%mBSljAOp<IYrF~g?lwiKg<llp)hoOCX@b+%{qD_FspL-QbCIqjtIK*=)=(X@)S)`hI+^VRuCcCiyJCfmt&2Mzk7s-FgEJEB'
    'WfE~l<my$}4+PLNizrb9IW2PaQUIkgTQ#u64Bvyx-1Rt=#CO%YIstU@vZXR&S1$!n%Y>L$TI?$1@EOj~3{Qm5PErcw#hH5+-(S9J'
    '4+LP0-z;YJDmk<fAP6+Kt63H3Jd|ZQ40P`uGA|1Bp6;wcwe<RAf&W<V!MocKbAKd*ukV63qh_UUP_xP^PizY#pUDv19^TF>J>5}('
    'YMb+2@4*+mDs*`~_mKM`b*|0gRnO)Yst;bop;lW}s%&n~3Os7qr<k)MK&jQ#QfghL>J}L;^)R5`>#cfKPuV5atTadr*{t{m7xzrA'
    '%79GI!&fO>;ROw-k~<dW3Yvm!y0Q$v0*%p&8Gf6e*Ij*t*nzZKRvoiLLqj;<t(r~j+jgt)hHLBnBrP}QMw#rrw&gSF4f#xk&*zR4'
    'x4NJo^-lUrgimSZjd^YTr3gbigYTlh6ahIc;c~}I>o2{Kqh+-AXl~bEG7n6kjxdac`^Ybu!*dxU9_Jlg+&0YUFTKj96afSc0&i9('
    'dZbEsL}BJMz1_rlj+b|ifIvu{<8`M<%IzYr%bRJkAuX|^_DPM>HHH%ud~<-Phx$;)iZwoWIjrFr;icJyWq|jMs7JUoYe6R8FqKEw'
    'E;75EnA*^vvifx01*wBJoGhS^u%QJBCX;Vij%m#N6>A18M7z5IElYk)>;AT#4xec*mFZ$SmuV!B`>PsLLyZJ>p*~QXDNWl~UCUQu'
    '2Q<S_pKL3`SKi%#n#M|ndd_GjSfA-F<*>$_QM1NqE(E-{4GAu|sR`9&14k)qxLv|k-pHVwqIS{X&@QXMs#6NjP@GV>_>{CIPlmcg'
    'rG3Y_d|gXVlaX742V^V}Mhjl}IZ0hjR@db)$A7DQ#*(`B0qkyKYelXmY^uU(x2y@PrYWT@dpw-x1y$XNpju@xURg<ZjAaoxGb~#a'
    'wjAD>le3aix)J#97DbRK)mF8k&ADiI_DYSg(t;^f+jdX4+d}|Af!``?^&<797@!2DJl-yAr60QLHj+F|c_&#b{eWdR0kZR?@@Y-s'
    'WMN#jPzBb~o-|eZ$Dtu!**UtG3A%Q&W$Hs$JDRmRn!JMJ&yKgyxD&hjn8DuA+6TPO))+2_{b?_mmAf)~J&?U80mCFinW5XISY+LT'
    'OHspg^<?>puz%~YiZY9U?f|--`moB*c9UjoyK+pU=M8JCr$V%Q+s`T|tyv_LH(y2`<_Sez-du{M-c9x-d`q!BREkA?ct9GlATfNP'
    'Xxkfd)m~FR<w+$^zJyFky`vmR_?9VoxJ(HRFtldUpfhW~@<gczZZdf5l4Z%}TMXAF>)hE2$PxvaJ@(YbaeVAkH(yM*?;yl<C0jMR'
    'vKUw>!N)6gb41-20_WX=+CSTBFGn{z{9<kQZX@o!9e?kUmYg<2@=r3>>p5sUk6kwC_)4f6;49mzsp|X3z4V6_9<{Yua(_9j;jrtm'
    '%QC?G+K}LKbTX@zl8VWZhc*KnU>f>rXdN20Z5wYStw${ZWJQwu+Yr1$n~7bPV;XaaU@h)dh<0}af;U!RCV?Oo6^}c#Q;I&E(p3iH'
    '5%w|q&`1b0zVNb(H=%g8Ibd8Ra5QJ2bJ;|Ka(H9nIS9-TtQ&#vZc`Lsy?IwUwD~xV`R_`H?g0Y8RzCDg0h9{fmM7f<oE1WOC!TZ!'
    's1oqfH0fLTK8M58QeUprlc7n!l>PK9=v+dhewCPQ1Zd=<gf(ssD-`f`3YG8+*ujNi1$ZMq_EmTKQhe;bFT3R)6b|Ex7B_5iXSqci'
    'wafL6o80gQ<nEj9^`*$(CK3wKZzX%bkV_#2i?3YdNM}gkw*Zt60!ppE>{(>E;4kD^NIDYh>kJ3{wE%j#NXdW|M)y^|Q(@9V32Qo;'
    'YH&3-{JxCt&3@gzy$o8D8*36~M^R6LL>sGgWW9`yVP?H!Xc!*E(!R1?_nm>s{>E;mZHw8!cCpm(u>+VE((0}3?6ktdgS>t%r2#C>'
    '3-?c^%NYS!1@2wh*aVQ4TEe|J8@q>r+Pw=MI|4#6-(G$nIyM2cLOcK3bZkZ;wRLYp$BuxU^^>{<YEn2vc+EjxS_TSEvBnx>DSIjB'
    '!NzX3sH16F#)1G4I!^co=gk4B=mg0LGh3Bc`mAh7F`}_=!bKPPEEHadb>FaQL~5<I874t0Ltd%{SeVv*X>AvU;6)=XUm2PTjxnDn'
    'N65(xm0$y?;efTmFNJV-x1g7cdf81)zdl+Jd66B0)xIGQF=!7$a^{BAbFds9n6P-Itm2hU)8P4eWk;*mNMb#C|97`2O-jzFIXR^1'
    '_X?v$%R!Fg=Kwa%;k^$2-WDeCEKQnW@un!L66fGYKXQ0SW!DHFtgEHzFev9;b%5T5`A}M+w0ZV!Ijpl>Q@iq(mI2<|hKgozrPGsS'
    'YWSDcBH?I2a>A_~MokH4bi*~sst&tDMp>=s4VuZmpU;xzkj5mV&q#5?dWB&3wjM#X=v5};FO|tA7a3K~PO~;^i}5j8>LC(>HkE1)'
    'P%9x&P9YkdN%<=WHOiIPwVcgDxVu}BhH!_8I7FJQeaos`J!Fw&Xp|xM<0{rRURa$!RB$uGDPE&*<k~!9jZSdT$mu`=<~;MX5fCdK'
    'by!1P(OK$pTs=v4i>aKxciz!z;o@v*R26C&XyxxZep@$N>e_eA0w~ll&pb8f+uY^w#wmS(nan)h2z>9Mg<u2C1Btrm8&YKo*okk>'
    '3dVQl7Z)Z1m9Sl(k*WNQ{9^cKDnFE|Y(6{yD(@46BeMIXu1>tlvMj#@>lxplLA^1#EYIS7RyOvtGN|F3js0*oHV>lSD(f<&(G(L>'
    'Eg}-Uy>`B8NEKZ^Y}LT!Ze{`h1$nd_-e{KrW^&cA5%}J#27*oN0-GrloT_=N7CYKqJLPu!s*3bJ=GxXaDAOrdSr)D8x&t_f@F8iE'
    '(<WObxE$SRympP-y%G1mCXJ{;Vsh(65C00ZS`0#VcXhqsgPt+{fypiB)LyExi?EQN1`UwLqh1160PpOgM|r@OGkj>IUNj8@O}3oN'
    'A&o=4Ukex%g5A3_5map_>0GqZZq9d#s#etfwue+r9h7gHz&ojG868p6kU`BF2y~@201eRnIt1Q?xx4)g^1tUXpXS_I+<@wHqje=}'
    'P>6SL6B<O}U2;5-oz~<h*N%xcaS10s^YKm~>`9$5^#9dj9Z&cn973Noi@83<K)WagZ^)hT!P4D34ulTpt2T5o@TC!X<GmGDbKnc1'
    'i2*T-Xqnef>wvaD-x@w|T2#FGpE`dc<8)3@v&Qz*Z>PQ=dP9N*8#(7RPPKx+!EH5Y;#?tvcl5Pdd2UlDbQtiuCOD4A(lwp&^ldq$'
    'k`n+>bd`it;?nS>!1c@HmgXL$tI0D^V;W)1kUBkawnywRgH29|`0sOU!&D16F1PX0-!;k>L3hLF*ilb@F$X1PCXZifvH!i{Q(zT5'
    'n=D>R_k;cp!{;=YGq$h)JiRdXLJAlE|D9(bAnPcf+`VtzsC}WU_$~y|HarN>gFG2zc0Q4UHuQ<1Ck_2(=wn0AC_A{9&HK>MBhSa1'
    'c2IAp&!IOCefW|^#u?@0We(@f=i3~AFZ2>OG^d@s(a=+-wCO+V&(HoouK&9`U0;d*ygqAZXaXJjtahlvvj`P%Z0o$2pSK-m$`A9u'
    '$6lz!BM&wG{ox%{;*xU38y;r%S$c$<e;IR4T8w4mRnswT=xyg?+UJ|IwLxcNV8Q1z95$0?`%LXzJMOp>5@!@tZnjx4nIbMtY4ZmB'
    '!VUP#Uw{1k?e~BC<A0ta?SK8rr+)q0hPF6|ld5EM_hI=c=9BAgEtxUb9{EuGBnSO*&xBqYn`y}A4X$OAHZ;a-a3*7+E8n8q+5}p_'
    '^E@H&`stpKbt+dLCsE@?EhN#%y_)1|Q~_dURi%}*o_D{<QSA=fb%hTnS%@%S6{i^8*_wMLRbwOWy;tP4MimM$lgF1zPg9GOH|eI?'
    '?%rS&I8>cx1vK5X*d36^N1(`&cRA(0a!ljD-CDAHA==#yhysMkW<p<1@73bMrsibTk}4H+*ei*=%0yVnh%SY9w!s<l@8m|{dz+MC'
    'd+Dc%;2WR#Z-4yLkKcd(?a#mb{_Bsw6#uZd!un}FR=o-F<Y#%B+49pUoWAhW0i~w5N)>x-=Z*OJA7p^?Cr|$;#LSt_wj$-MP1~^P'
    '_c5V|_Xd)U_9JfTysctm#3!{f@2c1s0jh<ni&|A|d=*M<571h(Rk88e#1A46>WTQS+KfHGgizEQNHa!!#<<PWj4$=75spPPu-=^9'
    't=7|3Uq+iz%xNcU>LcaJ-MTAC?#4ZeSR~WLuewt@O&l-SZoK0Q=|(0~vo}AlyT&j3SJow7SaMy}4f>NRmn!)p`jaAeuTQm|YtoB#'
    'mrXCmYf80TOikW&?R)E7UQGEdd_H#!`tWNA@_jWjEh~^oJ+0_Gt}-$jnIQ+zu<H|^2%uN$UBxjYKw5n0cNNEs0QI!?MBFmnOx=4z'
    'ZOl<nP8QtpD`{i)R(A+rN*nV`U+~hszLGX3cL42SmTx`IOlfV*7h06-`OG_MRcQfU{YXi<h{6c3OJx!^mHyPnOUgw+DCE0JXc9h9'
    '#@iQ{(2Otuy?GZ2O$Nk5UzZ~`841l7+GVwpx}LdNL-V1fL3$YI?;@f3fGQ9X50|Q)=B4=aRHNE8hJ*AHtn#dzBATx9MrpH1HImc3'
    '6eB_;+L31i9)oH`Wh%UTUW)yYLV2+Be1-^Xv_?6sv4_gF)RaQN`{pq)T>iW~XQc(EUS|nt6o7R4Dq*QDtD`#)9Sp;HxR0cie!!eX'
    'fV`C%o?wdorrrD<^VKv<(JQ7I1}kjsTP_o71ysjz!|exf8j{QM1<TP5$A~h`Bi@F4?~#O1)9^Q?eyT}%+Qx>ccvT5W&x6iFW2=fl'
    'FQgU0NqPPr*6h#Im5M8AGws@<scNG-Y`QqnnckhD^(G!-VoQ!5ED}*C)oRPpjtr#%b;88@*5|Od$>}L5r|hd~h<z)6eJg(zZjltB'
    '`_>Tq)(~3`jvky)(!IKd*thQ2rgnV^-LFksu`3wAHN>`I{7M>PmMI7M#XA-yWXXpnWO++7fzhSK!SLx)SqK0~Co>y;sog6hlbphn'
    'wLtXCBx`5|?1Ktj9j_d1+&Xu_lFofd)@WMD{7g6g%3+q03)Qs`VBfV|gl{IQCv#!9luVgfNS^^rg|`~#<7Nj2SJ!n=E&cxi!cBz9'
    'Thvo2qlKbdIjnJ+4r}6Dg@AWAp?4e^&d9W<G{+4r1Q#38oWG_5OcNE*jYU>KuUZBCn1tyB&ncZ#$GoP>TPti<t-T!OIF}7*lW*yj'
    '`1dw3p?BW9Rk6OQNY`EGHy7nC>~eE@3}H{3c$pu6$N4KZ&?DaNMm#dF8$aUqp2b&nBO(BlUcD=G61i-=(eSR!$%t>}A-xlEvd1^o'
    '#yJC+CQiN-Kx>5EN}PNxfL?7TR4$pJ>hVAv*mosPMtqnUD&K%N+2ixea?|*NyvfbmDH{s)6tt-@G*)n@!hlu@5AeyjiTCzArSMZ#'
    '=kv~toLl{RoWe~Ux{ak&vhCOyy2#$^y}5n&U5!ZP<yLy$t0Zd^Jl02YiN#2op7(^F5CO6JU0HY$pOy3MZMDY2lVZiy`%EQz0)S4S'
    'zKVu7p}eJoY)8}au5yVAvpWhLzQXK|N75{Mvpbt+;o0k1c(QsB3vZLpurVC1b__=!&q85)Yc<*2D;9(M`QumCIgNU3|Ne(R{QU9T'
    'MrpeE<J!4gt*KPuB(so{)YY^uk*i%4jpPUs#sHnwT*gU2D-NhjMBp@w*XL_ZmBagd>(&YrZ3Mn=tRuqa%1T>lj_Gat2Q8ko1eYvr'
    'z1X&&=GLqYIEOgOG(UTl5IjuNX<ukB$_Q)WW;(5T@FLyN>muD<=(Oe`3pDa!l~nJ_rzL>ky*KdMd|HBGg-5C1g-^?X=wH(XnOdjQ'
    '>Ri8z#d37A-^s`HKS!-bcNMMne1g?y1NkE-TBgt3iC$|SG5$GeteMKbH_iE84QlcWL$IBrGbZTT$<}v<MK@+nUpo{9JDrtW6pF9Z'
    '4c#l2H&ZNxPW{#)_2Ikww3-@Zrs5A|l?ZRNN;$l7V@G~gbGz)*ZUnx!PphSr#&2b#K3gV=k;*}FKC64WL=+=6Z?U~A>zM#*g%;Io'
    'vz{XipI!mJ9P60@QR}kBSyH7&V3CemS<y{0G#vt8*;XyRoIwd~4X@U_O7`D#EpoTL`_K+Xp+d}7X(@*}93$Lxisp3>VDBLwXtAU<'
    'X6mQbtqyHfnYH?<CY%a@VjJaK&+DfSbr2hLiW$IF#bq3W)%0d_&g*a<8ZY_0s07yZP+DgtpAQx_pRYRK)h>O$Z<p?z{!Du2zf<2g'
    'r!qULwM}dnGztTMW2iA%cSBW5S$kQVpgPf4aAI8AH~Mm&RC4a>+R`VzM0DA*PO9Z6N%o!ANj-bA{M_T+hG&2B75MLSY+@{xW8>w+'
    '=NPd#iRl`Ec%3o*XXl1Hj>TCg^--JC1TlQhYY7fs<?v~ZTLj-O)&M-RK5FdX&O$m5we@EOQXM~ZYE-5CtVHVke-d-%&>@CyG<2Gw'
    'gALuH?1)8DXC3G(6iGer;^%E2y7q9)|4yf_9D4MgmK0y~fZ1p9QD6Iu%K>bDTpZBG%P$v6J?~BY_oV@Dy=AXgBvoWW@!v&K$7#h#'
    'M4j`SsxrSRWc(&_j^dXptf2}<8LXp!)CMD1%Io6!K>m~^7b|dm!7BP$h&5Is(4<7)r)j7T-tu|&U@HiUYi03yXVLfGPvw~1=M8<I'
    'RbYgR)0tJWt6K8E+R*U%wz6&X*R*%FBHsvW!RISuV|yx^U)j&H9zCCj7Giq<&@$Bw8pn@_+6!@?!#k@3`F#>?yno|N7teRt1W2DB'
    'Us<CkHRMy@?<&ES%td7y7uyS!LOJpK>e25rhMr}q-$xd!ZuI-AZ@+J!7gV7tb^EHM+gELI`-WaL^qHZ54ZY&q?fZ87zTLiWx9{8S'
    'dtJA0n%gwj9Y~SsVZr8B^2FjE6SwN9))46DYF5i@s<v{62|?lqDy~zQl^-ZaH;(c$&sCROaqqnWN~l42_~(BmF8H6n|0A4Tq2R-6'
    'Lld6**MIrHfBf&?|9g5fps5x9`Tu!Jhr|'
)

def recorded_ui173():
    raw = zlib.decompress(base64.b85decode(RECORDED_UI173))
    assert hashlib.sha256(raw).hexdigest() == UI173_FIXTURE_SHA256
    return json.loads(raw)

def recorded():
    raw = zlib.decompress(base64.b85decode(RECORDED))
    assert hashlib.sha256(raw).hexdigest() == FIXTURE_SHA256
    return json.loads(raw)


def proof(value=None):
    value = recorded() if value is None else value
    return sync.login_sync(*(value[k] for k in ('rows', 'events', 'session', 'since', 'until', 'baseline_pose')))


def packet(value, name, direction='from_client'):
    return next(r for r in value['rows'] if (r['name'], r['direction']) == (name, direction))


def change_body(row, offset, fmt, value):
    raw = bytearray.fromhex(row['body'])
    raw[offset:offset + struct.calcsize('<' + fmt)] = struct.pack('<' + fmt, value)
    row['body'] = raw.hex()


def native_creation(value):
    return packet(value, 'SMSG_UPDATE_OBJECT', 'from_native')


def change_creation_bit(value, bit):
    row = native_creation(value)
    raw = bytearray.fromhex(row['body'])
    raw[313 + bit // 8] ^= 1 << (7 - bit % 8)
    row['body'] = raw.hex()


def test_actual_921_packets_prove_exact_inert_login_and_json_roundtrip():
    value = recorded()
    result = proof(value)
    assert len(value['rows']) == 921
    assert value['failed_entry_sha256'] == 'cb64cec0472f9a23d176fbf1e98710aee72b0c195f03ca62b60355f7d994213f'
    assert result['instance_session'] == '04aa8d2f'
    assert result['clock_deltas'] == [1525, 250]
    assert result['initialization']['clock'] == 573091437
    assert len(result['allowed_packet_keys']) == 9
    assert len(result['allowed_metadata_keys']) == 15
    assert len(result['source_packets']) == 14
    assert len(result['source_events']) == 21
    assert result['heartbeat']['movement']['sin'] != 0
    assert result['heartbeat']['movement']['cos'] != 0
    assert result['self_creation']['movement']['speeds'][7] != struct.unpack('<f', struct.pack('<f', __import__('math').pi))[0]
    assert sync.validate_login_sync(json.loads(json.dumps(result))) == result
    for rows, session in ((value['rows'], value['session']), (value['events'], value['session']),
                          (value['events'], result['instance_session'])):
        contract.forbidden_packets(rows, session, value['since'], value['until'], login_sync=result)
    replay = contract.native_replay(value['rows'], value['session'], value['since'], value['until'], login_sync=result)
    assert replay['native_inventory_states'] == [[contract.SOURCE['guid'], contract.DESTINATION['guid']]]


def test_ui172_canonical_proof_is_byte_identical_after_causal_order_repair():
    raw = json.dumps(proof(), sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    # Captured before replacing the unsupported cross-stream ordering edge.
    assert hashlib.sha256(raw).hexdigest() == '657a55ffd0a537d7e9e74244f457ffd2185c8d1542e041e7ae0e68fd44031090'


def test_actual_ui173_complete_failed_entry_has_exact_causal_stationary_boot():
    value = recorded_ui173()
    assert value['failed_entry_sha256'] == '63e2bd045a162b7cb125f76dd3532ca0f43a3e77137ca9e02a7e8cfbf009329a'
    assert value['completed'] is False
    assert value['failure'] == 'RuntimeError: login settlement must be one ordered two-second initial prefix'
    assert (len(value['rows']), len(value['events'])) == (1202, 1493)
    result = proof(value)
    skipped = [r for r in value['rows'] if r['name'] == sync.SKIPPED]
    assert skipped[1]['time'] < result['heartbeat']['native']['time']
    assert result['session'] == '978efd24'
    assert result['instance_session'] == 'b47a0541'
    assert result['initialization']['clock'] == 583390009
    assert result['clock_deltas'] == [1714, 250]
    assert (len(result['allowed_packet_keys']), len(result['allowed_metadata_keys'])) == (9, 15)
    assert (len(result['source_packets']), len(result['source_events'])) == (14, 21)
    assert sync.validate_login_sync(json.loads(json.dumps(result, allow_nan=False))) == result
    for rows, session in ((value['rows'], value['session']), (value['events'], value['session']),
                          (value['events'], result['instance_session'])):
        contract.forbidden_packets(rows, session, value['since'], value['until'], login_sync=result)
    replay = contract.native_replay(value['rows'], value['session'], value['since'], value['until'], login_sync=result)
    assert replay['native_inventory_states'] == [[contract.SOURCE['guid'], contract.DESTINATION['guid']]]


def retime_packet_and_metadata(value, row, timestamp):
    """Keep the retained packet and its logging/submission metadata coherent."""
    candidates = [e for e in value['events'] if (e.get('name'), e.get('direction')) ==
        (row['name'], row['direction']) and e.get('event') in ('modern_packet', 'native_packet') and
        0 <= row['time'] - e['time'] < .1]
    event = max(candidates, key=lambda e: e['time'])
    delta = timestamp - row['time']
    row['time'] = timestamp
    event['time'] += delta
    if row['direction'] == 'from_client':
        for effect in value['events']:
            if effect.get('event') == 'movement_forwarded' and effect.get('name') == row['name']:
                effect['time'] += delta
    value['rows'].sort(key=lambda r: r['time'])
    value['events'].sort(key=lambda e: e['time'])


@pytest.mark.parametrize('interleaving', ['after_skip', 'after_modern_land'])
def test_native_heartbeat_queue_can_complete_after_a_subsequent_modern_packet(interleaving):
    value = recorded()
    native = packet(value, 'MSG_MOVE_HEARTBEAT', 'to_native')
    before = [r for r in value['rows'] if r['name'] == sync.SKIPPED][1] if interleaving == 'after_skip' else packet(value, sync.LANDING)
    after = packet(value, sync.LANDING) if interleaving == 'after_skip' else packet(value, 'MSG_MOVE_FALL_LAND', 'to_native')
    retime_packet_and_metadata(value, native, (before['time'] + after['time']) / 2)
    result = proof(value)
    assert before['time'] < result['heartbeat']['native']['time'] < after['time']
    assert sync.validate_login_sync(result) == result


@pytest.mark.parametrize('fault', ['modern_order', 'native_order', 'native_before_modern', 'journal_order'])
def test_actual_ui173_causal_stream_or_pair_order_cannot_be_coherently_relabelled(fault):
    value = recorded_ui173()
    heart = packet(value, sync.HEARTBEAT)
    native_heart = packet(value, 'MSG_MOVE_HEARTBEAT', 'to_native')
    if fault == 'modern_order':
        skipped = [r for r in value['rows'] if r['name'] == sync.SKIPPED]
        retime_packet_and_metadata(value, heart, (skipped[1]['time'] + native_heart['time']) / 2)
    elif fault == 'native_order':
        retime_packet_and_metadata(value, native_heart, packet(value, 'MSG_MOVE_FALL_LAND', 'to_native')['time'] + .0001)
    elif fault == 'native_before_modern':
        retime_packet_and_metadata(value, native_heart, heart['time'] - .0001)
    else:
        index = value['rows'].index(heart)
        other = value['rows'].index(native_heart)
        value['rows'][index], value['rows'][other] = value['rows'][other], value['rows'][index]
    with pytest.raises(RuntimeError, match='ordered|forwarding order|extra, repeated'):
        proof(value)


@pytest.mark.parametrize('fault', ['raw_flags', 'native_body', 'metadata_owner', 'metadata_time',
    'raw_duplicate', 'metadata_duplicate', 'later_movement', 'late_prefix'])
def test_actual_ui173_interleaving_does_not_relax_exact_bytes_metadata_or_boot_scope(fault):
    value = recorded_ui173()
    result = proof(value)
    heart = packet(value, sync.HEARTBEAT)
    forwarded = next(e for e in value['events'] if e.get('event') == 'movement_forwarded' and e.get('name') == sync.HEARTBEAT)
    if fault == 'raw_flags':
        change_body(heart, 5, 'I', 0x801)
    elif fault == 'native_body':
        packet(value, 'MSG_MOVE_HEARTBEAT', 'to_native')['body'] += '00'
    elif fault == 'metadata_owner':
        forwarded['session'] = 'another-physical-instance'
    elif fault == 'metadata_time':
        forwarded['time'] = packet(value, 'MSG_MOVE_HEARTBEAT', 'to_native')['time'] + .0001
    elif fault == 'raw_duplicate':
        value['rows'].append(deepcopy(heart))
    elif fault == 'metadata_duplicate':
        value['events'].append(deepcopy(forwarded))
    elif fault == 'later_movement':
        value['rows'].append({**heart, 'time': value['until'] - .01})
    else:
        # Keep both streams, every native pair and all metadata latencies exact;
        # only the delivered-world two-second boundary is exceeded.
        for row in value['rows']:
            if row['name'].startswith(('CMSG_MOVE_', 'MSG_MOVE_')) or row['name'] == sync.ACTIVE:
                row['time'] += 2
        for event in value['events']:
            if str(event.get('name', '')).startswith(('CMSG_MOVE_', 'MSG_MOVE_')) or event.get('name') == sync.ACTIVE or event.get('event') == 'native_active_mover_confirmed':
                event['time'] += 2
        value['rows'].sort(key=lambda r: r['time'])
        value['events'].sort(key=lambda e: e['time'])
    with pytest.raises(RuntimeError):
        proof(value)
    if fault in ('raw_duplicate', 'later_movement'):
        with pytest.raises(RuntimeError):
            contract.forbidden_packets(value['rows'], value['session'], value['since'], value['until'], login_sync=result)
    elif fault == 'metadata_duplicate':
        with pytest.raises(RuntimeError):
            contract.forbidden_packets(value['events'], result['instance_session'], value['since'], value['until'], login_sync=result)


@pytest.mark.parametrize('name,offset,fmt,replacement', [
    (sync.HEARTBEAT, 5, 'I', 0x801), (sync.HEARTBEAT, 9, 'I', 0x400),
    (sync.HEARTBEAT, 13, 'I', 1), (sync.HEARTBEAT, 21, 'f', -8914.0),
    (sync.HEARTBEAT, 33, 'f', 5.8), (sync.HEARTBEAT, 37, 'f', .1),
    (sync.HEARTBEAT, 41, 'f', .1), (sync.HEARTBEAT, 45, 'I', 1),
    (sync.HEARTBEAT, 49, 'I', 1), (sync.HEARTBEAT, 53, 'B', 0x21),
    (sync.HEARTBEAT, 54, 'I', 1), (sync.HEARTBEAT, 58, 'f', .1),
    (sync.HEARTBEAT, 62, 'B', 0x81), (sync.HEARTBEAT, 63, 'f', float('nan')),
    (sync.HEARTBEAT, 67, 'f', 0), (sync.HEARTBEAT, 71, 'f', .1),
    (sync.HEARTBEAT, 71, 'f', -0.0), (sync.LANDING, 9, 'I', 0),
    (sync.LANDING, 5, 'I', 0x800), (sync.LANDING, 53, 'B', 1),
])
def test_hidden_modern_flags_displacement_forces_and_momentum_fail(name, offset, fmt, replacement):
    value = recorded()
    change_body(packet(value, name), offset, fmt, replacement)
    with pytest.raises(RuntimeError):
        proof(value)


@pytest.mark.parametrize('bit', [0, 8, 32, 38, 39, 40, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 54, 55, 56, 57, 63])
def test_native_creation_controls_discarded_by_shared_parser_fail(bit):
    value = recorded()
    change_creation_bit(value, bit)
    with pytest.raises(RuntimeError):
        proof(value)


@pytest.mark.parametrize('fault', ['embedded_guid', 'native_pose', 'native_nonfinite', 'duplicate_creation',
    'creation_trailing', 'wrong_login_pose', 'wrong_baseline_pose', 'baseline_bool', 'baseline_inf',
    'wrong_init_clock', 'wrong_active_guid', 'wrong_turn_rate', 'turn_trailing', 'skip_clock',
    'skip_guid', 'skip_trailing', 'clock_wrap', 'wrong_native_body', 'native_before_modern',
    'late_native', 'missing_land', 'duplicate_heartbeat', 'late_heartbeat', 'forwarded_skipped',
    'modern_trailing', 'modern_foreign', 'unexpected_jump', 'bool_time'])
def test_original_prefix_cannot_admit_changed_or_additional_packets(fault):
    value = recorded()
    heart = packet(value, sync.HEARTBEAT)
    land = packet(value, sync.LANDING)
    if fault == 'embedded_guid': change_body(native_creation(value), 341, 'B', 4)
    elif fault == 'native_pose': change_body(native_creation(value), 333, 'f', -8914.0)
    elif fault == 'native_nonfinite': change_body(native_creation(value), 321, 'f', float('inf'))
    elif fault == 'duplicate_creation': value['rows'].append(deepcopy(native_creation(value)))
    elif fault == 'creation_trailing': native_creation(value)['body'] += '00'
    elif fault == 'wrong_login_pose': change_body(packet(value, 'SMSG_LOGIN_VERIFY_WORLD', 'from_native'), 4, 'f', -8914.0)
    elif fault == 'wrong_baseline_pose': value['baseline_pose'][0] = -8914.0
    elif fault == 'baseline_bool': value['baseline_pose'][0] = True
    elif fault == 'baseline_inf': value['baseline_pose'][0] = float('inf')
    elif fault == 'wrong_init_clock': change_body(packet(value, sync.INITIALIZE), 0, 'I', 1)
    elif fault == 'wrong_active_guid': packet(value, sync.ACTIVE, 'to_native')['body'] = '1004'
    elif fault == 'wrong_turn_rate': packet(value, sync.TURN)['body'] = struct.pack('<f', 3.14).hex()
    elif fault == 'turn_trailing': packet(value, sync.TURN)['body'] += '00'
    elif fault == 'skip_clock': change_body(packet(value, sync.SKIPPED), 5, 'I', 1526)
    elif fault == 'skip_guid': change_body(packet(value, sync.SKIPPED), 2, 'B', 3)
    elif fault == 'skip_trailing': packet(value, sync.SKIPPED)['body'] += '00'
    elif fault == 'clock_wrap': change_body(heart, 17, 'I', 0xffffffff)
    elif fault == 'wrong_native_body': packet(value, 'MSG_MOVE_HEARTBEAT', 'to_native')['body'] += '00'
    elif fault == 'native_before_modern': packet(value, 'MSG_MOVE_HEARTBEAT', 'to_native')['time'] = heart['time'] - .01
    elif fault == 'late_native': packet(value, 'MSG_MOVE_FALL_LAND', 'to_native')['time'] += 2
    elif fault == 'missing_land': value['rows'].remove(land)
    elif fault == 'duplicate_heartbeat': value['rows'].append(deepcopy(heart))
    elif fault == 'late_heartbeat': value['rows'].append({**heart, 'time': value['until'] - .01})
    elif fault == 'forwarded_skipped': value['rows'].append({**packet(value, sync.SKIPPED), 'direction': 'to_native'})
    elif fault == 'modern_trailing': heart['body'] += '00'
    elif fault == 'modern_foreign': change_body(heart, 2, 'B', 3)
    elif fault == 'unexpected_jump': value['rows'].append({**heart, 'name': 'CMSG_MOVE_JUMP'})
    elif fault == 'bool_time': heart['time'] = True
    with pytest.raises(RuntimeError):
        proof(value)


@pytest.mark.parametrize('fault', ['instance_account', 'duplicate_instance', 'instance_owner_session',
    'instance_time', 'missing_drop', 'drop_native_session', 'drop_wrong_bytes', 'duplicate_drop',
    'missing_packet_event', 'event_wrong_session', 'event_wrong_bytes', 'event_wrong_type',
    'event_wrong_direction', 'event_latency', 'duplicate_packet_event', 'extra_native_metadata',
    'forwarded_wrong_owner', 'forwarded_pose', 'forwarded_time', 'forwarded_ignored_metadata',
    'missing_confirmation', 'wrong_confirmation', 'event_nonfinite', 'extra_late_drop', 'unknown_movement_event'])
def test_actual_packet_drop_and_effect_metadata_are_not_interchangeable(fault):
    value = recorded()
    events = value['events']
    instance = next(e for e in events if e['event'] == 'instance_authenticated')
    drop = next(e for e in events if e['event'] == 'unmapped_client_packet')
    modern = next(e for e in events if e.get('name') == sync.HEARTBEAT and e['event'] == 'modern_packet')
    forwarded = next(e for e in events if e['event'] == 'movement_forwarded')
    confirmed = next(e for e in events if e['event'] == 'native_active_mover_confirmed')
    if fault == 'instance_account': instance['account_id'] = 3
    elif fault == 'duplicate_instance': events.append(deepcopy(instance))
    elif fault == 'instance_owner_session': instance['session'] = value['session']
    elif fault == 'instance_time': instance['time'] = value['until']
    elif fault == 'missing_drop': events.remove(drop)
    elif fault == 'drop_native_session': drop['session'] = value['session']
    elif fault == 'drop_wrong_bytes': drop['bytes'] = 5
    elif fault == 'duplicate_drop': events.append(deepcopy(drop))
    elif fault == 'missing_packet_event': events.remove(modern)
    elif fault == 'event_wrong_session': modern['session'] = value['session']
    elif fault == 'event_wrong_bytes': modern['bytes'] = True
    elif fault == 'event_wrong_type': modern['event'] = 'native_packet'
    elif fault == 'event_wrong_direction': modern['direction'] = 'to_native'
    elif fault == 'event_latency': modern['time'] -= .2
    elif fault == 'duplicate_packet_event': events.append(deepcopy(modern))
    elif fault == 'extra_native_metadata': events.append({**modern, 'session': value['session'], 'direction': 'to_native', 'event': 'native_packet'})
    elif fault == 'forwarded_wrong_owner': forwarded['guid'] = 3
    elif fault == 'forwarded_pose': forwarded['position'][2] += .1
    elif fault == 'forwarded_time': forwarded['time'] = value['until']
    elif fault == 'forwarded_ignored_metadata': events.append({**forwarded, 'name': sync.SKIPPED})
    elif fault == 'missing_confirmation': events.remove(confirmed)
    elif fault == 'wrong_confirmation': confirmed['guid'] = True
    elif fault == 'event_nonfinite': drop['time'] = float('nan')
    elif fault == 'extra_late_drop': events.append({**drop, 'time': value['until'] - .01})
    elif fault == 'unknown_movement_event': events.append({**drop, 'name': 'CMSG_MOVE_JUMP', 'time': value['until'] - .01})
    with pytest.raises(RuntimeError):
        proof(value)


@pytest.mark.parametrize('fault', ['allowed_key', 'metadata_key', 'boot_end', 'source_body', 'wrong_session', 'extra_field'])
def test_supplied_proof_is_reconstructed_before_any_allowance(fault):
    value = recorded()
    result = proof(value)
    if fault == 'allowed_key': result['allowed_packet_keys'].append('{}')
    elif fault == 'metadata_key': result['allowed_metadata_keys'].append('{}')
    elif fault == 'boot_end': result['boot_finished_at'] += 1
    elif fault == 'source_body': result['source_packets'][0]['body'] += '00'
    elif fault == 'wrong_session': result['session'] = 'foreign'
    else: result['invented'] = True
    with pytest.raises(RuntimeError):
        contract.forbidden_packets(value['rows'], value['session'], value['since'], value['until'], login_sync=result)


@pytest.mark.parametrize('name', [sync.HEARTBEAT, sync.SKIPPED, 'CMSG_PLAYER_LOGIN'])
def test_noncanonical_packed_guid_cannot_hide_extra_zero_octets(name):
    value = recorded()
    row = packet(value, name)
    row['body'] = '03a002000408' + row['body'][10:]
    with pytest.raises(RuntimeError):
        proof(value)


def test_coherent_native_clocks_still_cannot_exceed_two_second_settlement():
    from tools.client_compatibility.world.movement import encode, parse
    value = recorded()
    for name in (sync.HEARTBEAT, sync.LANDING):
        modern = packet(value, name)
        state = parse(bytes.fromhex(modern['body']), 2)
        change_body(modern, 17, 'I', state['time'] + 3000)
        state = parse(bytes.fromhex(modern['body']), 2)
        native_name, raw = encode(name, 2, state)
        packet(value, native_name, 'to_native')['body'] = raw.hex()
    change_body(packet(value, sync.SKIPPED), 5, 'I', 4525)
    with pytest.raises(RuntimeError, match='clock'):
        proof(value)


@pytest.mark.parametrize('fault', ['missing_name', 'numeric_name', 'missing_direction', 'invalid_direction',
    'missing_body', 'uppercase_body', 'extra_field', 'list_direction'])
def test_malformed_extra_raw_rows_cannot_disappear_from_completeness(fault):
    value = recorded()
    result = proof(value)
    extra = {**packet(value, sync.HEARTBEAT), 'time': value['until'] - .01}
    if fault == 'missing_name': extra.pop('name')
    elif fault == 'numeric_name': extra['name'] = 12
    elif fault == 'missing_direction': extra.pop('direction')
    elif fault == 'invalid_direction': extra['direction'] = 'elsewhere'
    elif fault == 'missing_body': extra.pop('body')
    elif fault == 'uppercase_body': extra['body'] = extra['body'].upper()
    elif fault == 'list_direction': extra['direction'] = ['from_client']
    else: extra['hidden'] = 1
    value['rows'].append(extra)
    with pytest.raises(RuntimeError):
        proof(value)
    with pytest.raises(RuntimeError):
        contract.forbidden_packets(value['rows'], value['session'], value['since'], value['until'], login_sync=result)


def fresh_login():
    """Synthetic fresh epoch using the retained exact wire layout, without old receipt authority."""
    from tools.client_compatibility.world.movement import encode, parse
    value = recorded()
    value.pop('failed_entry_sha256')
    delta = 2000.0 - value['since']
    old_session = value['session']
    sessions = {old_session: 'fresh-native-owner', '04aa8d2f': 'fresh-physical-instance'}
    value['session'] = sessions[old_session]
    value['since'] = 2000.0
    value['until'] += delta
    for row in [*value['rows'], *value['events']]:
        row['session'] = sessions.get(row['session'], row['session'])
        row['time'] += delta
    clock = 710000
    change_body(packet(value, sync.INITIALIZE), 0, 'I', clock)
    for name, gap in ((sync.HEARTBEAT, 1525), (sync.LANDING, 1775)):
        modern = packet(value, name)
        change_body(modern, len(sync.ACTOR_GUID) + 12, 'I', clock + gap)
        native_name, raw = encode(name, 2, parse(bytes.fromhex(modern['body']), 2))
        packet(value, native_name, 'to_native')['body'] = raw.hex()
    return value


def test_fresh_session_time_and_clock_proof_is_serialized_and_reconstructed():
    value = json.loads(json.dumps(fresh_login(), allow_nan=False))
    result = proof(value)
    assert result['session'] == 'fresh-native-owner'
    assert result['instance_session'] == 'fresh-physical-instance'
    assert result['initialization']['clock'] == 710000
    assert result['since'] == 2000.0
    assert result['clock_deltas'] == [1525, 250]
    assert sync.validate_login_sync(json.loads(json.dumps(result))) == result


@pytest.mark.parametrize('event', ['instance_authenticated', 'native_player_created',
    'movement_forwarded', 'native_active_mover_confirmed', 'active_mover_deferred_until_player_create'])
@pytest.mark.parametrize('bad_time', ['missing', None, True, float('nan'), float('inf'), float('-inf')])
def test_foreign_actor2_metadata_is_typed_before_time_or_session_filtering(event, bad_time):
    value = fresh_login()
    extra = {'event': event, 'session': 'foreign-connection', 'time': bad_time,
        **({'account_id': 2} if event == 'instance_authenticated' else {'guid': 2})}
    if bad_time == 'missing':
        extra.pop('time')
    value['events'].append(extra)
    with pytest.raises(RuntimeError, match='actor2 login metadata'):
        proof(value)


@pytest.mark.parametrize('event', ['instance_authenticated', 'native_player_created',
    'movement_forwarded', 'native_active_mover_confirmed', 'active_mover_deferred_until_player_create'])
def test_finite_foreign_actor2_metadata_cannot_disappear_from_fresh_window(event):
    value = fresh_login()
    value['events'].append({'event': event, 'session': 'foreign-connection', 'time': value['until'] - .01,
        **({'account_id': 2} if event == 'instance_authenticated' else {'guid': 2})})
    with pytest.raises(RuntimeError):
        proof(value)


@pytest.mark.parametrize('direction', ['from_client', 'to_native'])
@pytest.mark.parametrize('bad_time', ['inside', 'missing', None, float('nan')])
def test_foreign_raw_login_cannot_disappear_before_the_unique_login_guard(direction, bad_time):
    value = fresh_login()
    extra = {**packet(value, 'CMSG_PLAYER_LOGIN', direction), 'session': 'another-native-owner',
        'time': value['since'] + .1 if bad_time == 'inside' else bad_time}
    if bad_time == 'missing':
        extra.pop('time')
    value['rows'].append(extra)
    with pytest.raises(RuntimeError, match='login'):
        proof(value)
