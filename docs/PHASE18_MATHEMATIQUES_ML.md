# Mathématiques et machine learning appliqués à PHerc0343P

Dans les trois régions du pilote, changer l’ordre des couches a laissé entre 0 et 15 pixels communs sur les 656 mieux classés aux deux pas testés. Dans les deux régions de réplication, décaler la grille au pas de 256 px a laissé entre 0 et 2 pixels communs selon l’ordre. Quatre idées aident à interpréter ces résultats et à construire l’évaluation d’encre qui suit. [Mesures sur les trois régions](PHASE18_CPU_PILOT.md)

## 1. Équivariance, échantillonnage et contexte

Un segmentateur dense est **équivariant à la translation** si déplacer l’entrée de $a$ déplace sa carte de $a$, soit $F(T_a x)=T_aF(x)$. Cette propriété vaut pour la convolution sur un domaine infini. Elle peut être perdue aux bords et après un sous-échantillonnage. Un exemple suffit. La suite $x[n]=(-1)^n$ donne uniquement $+1$ si on conserve les indices pairs, et uniquement $-1$ si on conserve les indices impairs. Le filtrage passe-bas avant sous-échantillonnage réduit ce repliement spectral. Zhang étudie ce mécanisme dans les CNN. Kayhan et van Gemert montrent séparément que le remplissage des bords peut rendre la position accessible au réseau. [Zhang, ICML 2019](https://proceedings.mlr.press/v97/zhang19a.html) · [Kayhan et van Gemert, CVPR 2020](https://arxiv.org/abs/2003.07064)

Dans notre cas, le pixel garde ses coordonnées dans le scan. Le décalage de la grille change sa position **dans la tuile**, les voxels observés autour de lui et sa distance aux bords. Le décodeur de Villa emploie aussi `GroupNorm`, dont la moyenne et la variance dépendent des activations de la tuile, y compris à l’inférence. Un changement de contexte peut donc modifier des scores jusque dans le cœur. Les décalages de 128 px du pilote mesurent l’effet combiné du recadrage. Pour départager les mécanismes, un essai ultérieur peut croiser des décalages de 1 et 128 px avec la distance au bord, en comparant le même cœur. [Décodeur épinglé de Villa](https://github.com/ScrollPrize/villa/blob/baf5e605bb42a3d55a62b7c5c728e0908137225c/ink-detection/optimized_inference/model_resnet3d_3d_decoder.py) · [Wu et He, ECCV 2018](https://arxiv.org/abs/1803.08494)

### Le recouvrement uniforme moyenne quatre origines de grille

Dans une zone intérieure couverte par toutes les tuiles, les origines du pas de 128 px se répartissent en quatre classes modulo 256 sur les axes V et U. À chaque pixel $p$, chaque classe apporte la prédiction d’une tuile. Si $s_q(p)$ désigne cette prédiction pour l’origine de grille $q$, on a exactement

$$s_{128,\mathrm{uniforme}}(p)=\frac{s_{(0,0)}(p)+s_{(0,128)}(p)+s_{(128,0)}(p)+s_{(128,128)}(p)}{4}.$$

La fusion Hann remplace les quatre coefficients égaux par des poids positifs renormalisés, plus forts vers le centre de la tuile. Elle peut atténuer les artefacts de bord si ces zones sont moins fiables. L’étude de Pielawski et Wählby mesure un gain de segmentation dans son propre dispositif. Chez nous, la pondération déplace des candidats et son effet sur les pixels d’encre reste à mesurer. Près des bords du fragment, la couverture doit être rapportée, car certaines des quatre prédictions peuvent manquer. [Pielawski et Wählby, PLOS ONE 2020](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0229839) · [Règles de fusion de la phase 18](validation/phase18-protocol.json)

L’audit a recalculé les 18 prédictions de tuile de la région centrale avec les couches 02–63. Sur 65 536 pixels, la moyenne des quatre grilles et le recouvrement uniforme coïncident exactement en `float32`, dans les deux ordres. L’écart entre le score maximal et le score minimal des quatre grilles, moyenné sur les pixels, vaut **0,194** pour `Z_in` et **0,355** pour `Z_out`. [Audit numérique](validation/phase18-rank-audit.json)

Les tuiles voisines partagent une partie de leurs entrées. Si leurs erreurs ont la même variance $\sigma^2$ et la même corrélation deux à deux $r$, la variance de leur moyenne est $\sigma^2(1+3r)/4$. Pour $r=1$, la variance de la moyenne est égale à celle d’une tuile. La dispersion entre grilles que l’on observe sans étiquettes mesure une sensibilité au tuilage. L’erreur de prédiction demande une référence.

Les origines de grille de l’essai complet comptent 1 180 tuiles au pas de 256 et 4 687 au pas de 128. L’ensemble au pas de 256 est inclus dans celui au pas de 128. Pour le même ordre et la même fenêtre Z, on peut réutiliser la prédiction d’une tuile dans les deux fusions. Cela ramènerait le plan de 21 108 à 18 748 inférences de tuile hors répétitions de contrôle, soit 11,2 % de calculs de tuile évités. L’égalité des cartes complètes resterait à contrôler sur CUDA. [Plan de calcul](validation/phase18-protocol.json) · [Nombre de tuiles](validation/phase18-prepare.json)

## 2. Symétrie de profondeur et biais inductif

L’inversion de l’ordre des 62 plans est une involution $R$ qui satisfait $R^2=I$. Sur une carte 2D de la même surface, l’orientation des plans change et la coordonnée du pixel reste fixe. On peut décomposer le score $f$ en une partie symétrique $f_+=(f+f\circ R)/2$ et une partie antisymétrique $f_-=(f-f\circ R)/2$. Ainsi $f_+(Rx)=f_+(x)$ et $f_-(Rx)=-f_-(x)$. La seconde composante mesure la sensibilité à l’ordre. La première garantit une carte identique sous renversement.

Pour une référence binaire $y$ commune aux deux représentations, le carré de l’erreur de $f_+$ vaut la moyenne des deux carrés d’erreur moins $(f(x)-f(Rx))^2/4$. Ce résultat porte sur la **moyenne des deux orientations** et sur une perte quadratique. Le gain sur la meilleure orientation et l’effet sur la ROC-AUC restent à mesurer. La théorie des moyennes sur les orbites explique quand une symétrie est un bon biais d’apprentissage. Une orientation physique standardisée peut exploiter la direction air–papyrus à travers différentes conventions de stockage. La moyenne des deux ordres est une autre hypothèse à tester sur des fragments annotés. [Chen, Dobriban et Lee, JMLR 2020](https://jmlr.org/papers/v21/20-163.html) · [Orientation de la pile PHerc0343P](PHASE17_ORIENTATION_2UM.md)

## 3. Stabilité du top 1 %, classement et calibration

**Une petite différence de score suffit si la marge au seuil est faible.** Pour des scores triés $s_{(1)}\geq\cdots\geq s_{(n)}$, la marge du top $k$ est $g=s_{(k)}-s_{(k+1)}$. Si chaque score bouge d’au plus $\varepsilon$, la séparation entre un pixel sélectionné et un pixel extérieur reste au moins $g-2\varepsilon$. La condition stricte $g>2\varepsilon$ garantit donc l’appartenance au top $k$. Si cette condition échoue, il faut observer directement quels pixels changent. Ce certificat est suffisant, et un maximum isolé peut le rendre conservateur.

| Perturbation sur le cœur central | Ordre ou pas fixé | Marge $g$ avant variation | Variation maximale $\varepsilon$ |
| --- | --- | ---: | ---: |
| Décalage de 128 px, pas 256 | `Z_in` | $2{,}80\times10^{-6}$ | 0,651 |
| Décalage de 128 px, pas 256 | `Z_out` | $1{,}73\times10^{-6}$ | 0,779 |
| Pondération uniforme vers Hann, pas 128 | `Z_in` | $9{,}09\times10^{-6}$ | 0,310 |
| Pondération uniforme vers Hann, pas 128 | `Z_out` | $2{,}15\times10^{-6}$ | 0,561 |
| Inversion `Z_in` vers `Z_out` | Pas 256 | $2{,}80\times10^{-6}$ | 0,776 |
| Inversion `Z_in` vers `Z_out` | Pas 128 | $3{,}14\times10^{-5}$ | 0,770 |

Pour les six comparaisons, la marge entre les pixels classés 656 et 657 reste sous $2\varepsilon$. Les contrastes d’ordre retrouvent exactement le recouvrement du pilote central, soit 0 et 15 pixels communs aux deux pas. Le certificat et le recouvrement apportent ainsi deux informations distinctes, une borne sur la stabilité et un changement observé. [Audit numérique](validation/phase18-rank-audit.json) · [Pilote central](validation/phase18-cpu-pilot.json)

**Spearman mesure le classement entier.** Dans un exemple sans ex æquo, échanger les $k$ meilleurs rangs avec les $k$ suivants en préservant l’ordre de chaque bloc déplace $2k$ pixels de $k$ rangs. La formule de Spearman donne alors $\rho=1-12k^3/[n(n^2-1)]$. Pour $n=65\,536$ et $k=656$, cela donne $\rho\simeq0{,}999988$ avec **zéro** pixel commun dans le top 1 %. C’est un exemple construit qui explique pourquoi le recouvrement du top $k$ complète la corrélation globale.

**La ROC-AUC mesure un ordre entre les classes.** Elle vaut $P(s^+>s^-)+\tfrac12P(s^+=s^-)$ pour une paire encre/papyrus tirée selon les règles choisies. Une transformation strictement croissante conserve ce classement. La même borne de perturbation montre que seules les paires dont l’écart initial vaut au plus $2\varepsilon$ peuvent modifier la ROC-AUC. Le seuil de 0,5 et la calibration des probabilités répondent à d’autres questions. Le score de Brier, par exemple, est minimisé en espérance conditionnelle par la probabilité $P(Y=1\mid X)$. [Bamber, 1975](https://doi.org/10.1016/0022-2496(75)90001-2) · [Gneiting et Raftery, JASA 2007](https://doi.org/10.1198/016214506000001437) · [Guo et al., ICML 2017](https://proceedings.mlr.press/v70/guo17a.html)

La précision dépend aussi de la prévalence $\pi$ selon $\mathrm{Précision}=\pi\,\mathrm{TPR}/[\pi\,\mathrm{TPR}+(1-\pi)\,\mathrm{FPR}]$. Avec une sensibilité de 80 % et 1 % de faux positifs, elle vaut environ 45 % si la prévalence est de 1 %. Le choix du papyrus négatif « propre » peut en plus changer le taux de faux positifs lui-même. Il faut lire l’average precision et la précision au top 1 % avec la prévalence et les règles du support. [Saito et Rehmsmeier, PLOS ONE 2015](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0118432)

## 4. Comparaison appariée et généralisation

Pour une métrique $M$, la différence $M(Z_{out},128)-M(Z_{in},128)$ isole le changement d’ordre à ce pavage. La différence entre ce contraste et son équivalent au pas 256 mesure l’interaction entre ordre et pavage. Les quatre métriques doivent utiliser les mêmes pixels, la même vérité de référence et la même règle de score. Le gain externe de **0,321** sur PHerc0343P vient des deux ordres au pas de 256 sur les mêmes pixels. La case en ordre stocké au pas de 128 manque pour calculer l’interaction externe. [Comparaison appariée d’EconLearn](https://github.com/ScrollPrize/villa/issues/2627#issuecomment-7209601820) · [Plan apparié de la phase 18](validation/phase18-protocol.json)

Les pixels voisins partagent le contexte du réseau et peuvent appartenir au même trait. La précision des estimations et la généralisation à de nouveaux fragments dépendent donc d’unités plus larges que le pixel. Dans la phase 18, le bootstrap rééchantillonne des composantes d’encre avec leurs négatifs associés en gardant les tirages appariés entre méthodes. Ce modèle de dépendance reste une approximation. La sensibilité à la taille des blocs et une évaluation sur des fragments réservés sont complémentaires. [Roberts et al., Ecography 2017](https://nsojournals.onlinelibrary.wiley.com/doi/full/10.1111/ecog.02881) · [Audit spatial de notre phase 15](PHASE15_AUDIT.md)

Les **lois d’échelle** relèvent d’un autre niveau de preuve. Une forme comme $L(N,D)\approx L_\infty+aN^{-\alpha}+bD^{-\beta}$ s’ajuste sur une série d’entraînements de tailles différentes, comme dans l’étude de Hoffmann et al. sur les modèles de langue. Nos essais font varier la recette d’inférence à poids constants. Pour estimer une loi d’échelle en détection d’encre, il faudrait varier la taille du modèle et les données d’entraînement, puis mesurer la perte sur des fragments réservés. [Hoffmann et al., section 3.3](https://arxiv.org/abs/2203.15556)

## Reproduire l’audit

Depuis la racine du dépôt, avec la pile préparée et PyTorch installé dans l’environnement Python.

```sh
python docs/validation/phase18_rank_audit.py --output data/phase18/rank-audit.json
```

L’audit lit le CT et le masque du pilote. La mesure de la ROC-AUC et de la précision sur l’encre est réservée au protocole complet. [Script et provenance des calculs](validation/phase18_rank_audit.py) · [Protocole](validation/phase18-protocol.json)
