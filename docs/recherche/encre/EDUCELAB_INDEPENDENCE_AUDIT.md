# EduceLab · Indépendance des fenêtres de référence

Les huit fenêtres de la phase 5 ont été revérifiées contre les
masques et photographies infrarouges publiés. Le script retrouve
leurs coordonnées et vérifie les 24 empreintes du CT, de l’IR et
des annotations. Les labels IR sont indépendants des prédictions
PHerc0500P2. Pour les deux modèles étudiés, l’exclusion de ces
fragments ou de leurs dérivés de l’entraînement reste indémontrée.
**Aucune des huit fenêtres n’est donc admise pour mesurer la
généralisation de ces checkpoints.**
[Manifeste de source](../../validation/phase5-reference-windows.json) · [Vérification phase 6](../../validation/phase6-review-windows.json)

| Fenêtres | Usage possible aujourd’hui | Condition pour l’évaluation |
|---|---|---|
| Frag1 et Frag3 `mask_edge_artifact` | QA sur la correspondance CT/masque et sur l’exclusion des bords. Les 8 161 et 8 078 pixels hors masque sont nuls dans le CT. | Exclure ces pixels du dénominateur. Conserver ces deux fenêtres comme contrôles de géométrie. |
| Frag1 et Frag3 `ink` | Comparaison visuelle exploratoire du CT à l’IR annoté sur la face exposée, respectivement 2 955 et 2 944 positifs. | Démontrer l’exclusion du rouleau parent et de tous ses dérivés. Rendre les prédictions à la même résolution et sur la même face. |
| Frag1 et Frag3 `sparse_traces` | Contrôle des traces rares, 166 et 158 positifs, utile à la relecture des faibles surfaces annotées. | Même condition, avec métriques présentées par strate et leurs effectifs. |
| Frag1 et Frag3 `background` | Témoin de fond, définit le négatif selon l’annotation. Frag1 contient 21 zéros CT dans le masque. | Documenter séparément le support d’acquisition. Garder hors évaluation les pixels dont le support est incertain. |

L’IR provient de photographies recalées sur la texture CT via
le repère de surface décrit par EduceLab. La coupe CT 32,
`uint16`, est un contrôle géométrique de ces zones à 3,24 µm.
Elle ne fournit pas à elle seule les 62 coupes adaptées au
checkpoint canonique à 2 µm. Les 48 labels de Frag3 hors masque sur
la surface entière sont exclus de la construction. Les codes
utilisés restent 0 pour le fond annoté, 1 pour l’encre annotée et
255 pour les pixels à ignorer.
[Construction EduceLab](https://arxiv.org/html/2304.02084v4#A8) · [Sources exactes et conditions](INK_EVALUATION_DATASET.md)

## Audit des entraînements

La fiche et les hyperparamètres du checkpoint A décrivent
l’architecture, le format CT et le numéro d’étape. Ils ne
contiennent aucun découpage de rouleaux. Pour B, le catalogue
renseigne des échantillons compatibles avec le rendu. Cette
métadonnée décrit la compatibilité d’usage. L’ascendance des
données d’entraînement et de pseudo-étiquetage reste inconnue.
Les familles de modèles présentées dans la publication EduceLab
et leurs résultats de validation concernent des expériences
distinctes. [Fiche canonique](https://huggingface.co/scrollprize/ink_canonical_2um) · [Évaluation publiée](https://arxiv.org/html/2304.02084v4#S2.SS2) · [Atlas](INK_PROVENANCE_AUDIT.md)

Frag1 appartient à Paris 2 avec Frag2. Frag3 appartient à Paris 1
avec Frag4. L’admission d’un test requiert la liste des rouleaux
ayant contribué à l’entraînement, à la pseudo-annotation et au
réglage de chaque checkpoint. On choisira un autre rouleau pour
fixer les seuils, puis on mesurera précision, rappel, FPR et
effectifs par strate sur le rouleau de test, avec un intervalle
d’incertitude qui tient compte du regroupement spatial des pixels.
Sans preuve d’exclusion, seules les mesures descriptives et les
contrôles géométriques sont rapportés.
