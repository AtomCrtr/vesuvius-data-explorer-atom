# Demande scientifique aux auteurs de l’étude de profilométrie

Brouillons locaux à approuver avant envoi. Premier interlocuteur proposé, **Giorgio Angelotti**, premier auteur de l’étude et responsable du Vesuvius Challenge, à l’adresse professionnelle `giorgio@thegiorgio.org`. Il pourra orienter les demandes liées à la campagne optique vers les co-auteurs. Pour la cote et les droits photographiques, le service public de l’Officina dei Papiri Ercolanesi publie l’adresse `bn-na.papiri@cultura.gov.it`. Pour le checkpoint A, demander au mainteneur de la recette canonique l’ascendance attachée au SHA-256 exact. [Coordonnées de l’auteur](https://thegiorgio.org/#contact) · [Officina](https://www.bnnonline.it/it/121/officina-dei-papiri-ercolanesi) · [Étude de profilométrie](https://doi.org/10.1038/s41598-026-58467-1)

## Version courte pour Discord

> Hi Giorgio! I’m working on [Vesuvius Explorer](https://github.com/AtomCrtr/vesuvius-data-explorer-atom), an open-source CT tool. We reproduced the published canonical 2 µm A map within one 8-bit level on a checked crop and measured the effect of reversing input depth. We found the public M1050 IR no. 017 JPEG and the legacy frontal set. Could you confirm the photo reference and share an overview locating all four PHerc. 500P2 optical fields, starting with `500P2_230925_N2`, plus any landmarks or transforms to frontal CT? Could you clarify the 0.68793625 versus 0.34 µm/pixel calibration, including any export or resampling steps? We’d also value a pointer to the exact canonical A training surfaces and labels. Please let us know the access and reuse terms.

## Version professionnelle pour email

**Subject** — PHerc. 500P2 profilometry field locations and CT registration provenance

> Dear Dr Angelotti,
>
> I am writing on behalf of [Vesuvius Explorer](https://github.com/AtomCrtr/vesuvius-data-explorer-atom), an open-source tool for inspecting CT volumes, traced surfaces and ink scores. On a verified PHerc. 500P2 crop, we reproduced the published canonical 2 µm ink map to within one 8-bit level. With the same public checkpoint and tiling, changing only the order of the depth slices produced substantial, spatially variable changes in its scores. We would like to check those scores against an independent observation of ink, starting with one field from your profilometry study (doi:10.1038/s41598-026-58467-1).
>
> Could you help us locate the four PHerc. 500P2 fields acquired on 23 September 2025, `500P2_230925_H`, `500P2_230925_IT`, `500P2_230925_N` and `500P2_230925_N2`? We plan to start with N2. A photograph of the whole fragment with the four footprints and the acquisition direction marked would help. If the stage coordinates or geometric landmarks are available, we would also welcome their coordinate convention and a link to the relevant CT acquisition and segment or rendering revision.
>
> Extended Data Fig. 5 in arXiv:2606.29085v1 names Naples M1050 IR photograph no. 017. We found `PHerc.500 ACass.28+M1050IR_017.jpg` and `500P2_ir.png` in the public archive. Could you confirm the input photo and archive reference, the face used in the profilometry campaign, and the exact CT raster and revision behind the figure? The legacy frontal image and the current Atlas canvas have different dimensions. Could you share the original alignment points or transform and any crop or orientation parameters, so we can reserve some landmarks for an error estimate? If a different photograph or higher-resolution source is the appropriate bridge, we would welcome a pointer or an authorized crop.
>
> Could you clarify the physical lateral pitch? The N2 coordinates give 0.68793625 µm/pixel in the released file and the manuscript gives 0.34 µm/pixel. The original objective or stage calibration and any binning, stitching, resampling or export software settings would help us determine how the two values relate.
>
> Finally, could you point us to the training, tuning and pseudo-labelling manifest for the production ResNet-152 checkpoint `new_canon_autoresearch_recipe` (SHA-256 `36dd0de84b7b7aa6590184192c7415466cd8a1ba7c1e59f42c6373846373c3e0`)? We would like to check whether these PHerc. 500P2 fields, their IR or CT derivatives, or PHerc. Paris 1 or Paris 2 fragments intersect the training data. The specimen and surface identifiers, CT revisions and labelled footprints, or an explicit exclusion list, would already help.
>
> Please let us know what can be accessed and under what terms, including whether we may share derived landmarks, registered crops or summary measurements. An annotated overview, a coordinate table or a referral to the appropriate data custodian would be a helpful first step.
>
> Best regards,
>
> The Vesuvius Explorer project
