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
