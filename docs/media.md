# Editorial images

`content/media.json` is the curated image registry. It maps article slugs and resource IDs to local assets, independently of the Awesome catalog importer. Catalog imports must not rewrite this file.

Use relevant photographs, project marks, author-supplied figures, and real interface screenshots. Articles without a suitable image remain readable text. Do not invent a project logo or represent an illustration as documentary photography. Archive photographs carry their original dates in captions. A project screenshot or published chart is illustrative source material, not an experiment performed by Audit Commons.

## Adding an image

1. Verify the source page, rights statement, depicted subject, and relevance to the entry. Prefer the project's own repository or documentation, licensed photographs, and public government material.
2. Store the unmodified asset in `assets/media/`. Record its source and download URLs, credit, rights or license link, retrieval date, SHA-256, intrinsic dimensions, descriptive alt text, and a factual caption. Retain applicable license and notice files under `assets/media/licenses/`.
3. Map the article slug or resource ID to the asset key in the registry. Use `photo`, `logo`, `screenshot`, or `figure` to select presentation. The build rejects broken mappings, missing credits, missing assets, digest changes, and active or externally dependent SVG content. Embedded PNG/JPEG data in an upstream SVG is supported.
4. Build and check desktop and mobile layouts. Display marks and scientific figures without cropping or distorting them. The full local image is accessible from article figures; resource images open their resource. Avoid large downloads and do not add tracking pixels or hotlinked image dependencies.

Article captions show credits and rights links. Resource cards place these in their provenance details. Compact homepage thumbnails link to the corresponding attributed article or resource. Informative images have alt text and fixed intrinsic dimensions; images below the lead are lazy-loaded. Article images also supply structured-data metadata. Raster photographs and figures at least 600 pixels wide can supply social previews; screenshots, SVGs, and smaller images retain the site's raster social-preview fallback. This keeps scores inside example interfaces from being mistaken for editorial findings in caption-free share cards. Article images are not enlarged beyond their intrinsic dimensions.

The initial set is about 3.8 MB in total. Browser verification measured roughly 2.4 MB of media after scrolling the full homepage; lazy loading reduces the initial load. Images are currently preserved at their sourced dimensions. Future image additions should consider appropriately sized upstream thumbnails or explicitly documented derivatives, rather than increasing full-page transfer indefinitely.

## Rights

Each image retains its own rights. Repository licenses are recorded from the upstream project; they do not grant ownership of trademarks. Logos and project banners identify the subject of an editorial listing and imply no affiliation or endorsement. Upstream copyright and license notices are retained alongside the assets. These image-specific permissions do not set the license of the Audit Commons website.

The initial set includes licensed archive photographs of Dario Amodei and Sam Altman, NIST campus photography, the METR mark, an author-supplied optstop figure, Inspect's documented log viewer, and project marks or previews for selected resources. The registry is the authoritative per-image provenance record.

## Editor Portrait

The About editor profile uses `assets/media/yue-zhao.jpg`, copied without modification from Yue Zhao's current homepage asset, `images/rsz_300.jpg`, on September 22, 2026. Its actual dimensions are 1024 by 1024 pixels. Yue requested this use; no general reuse license or photographer attribution is inferred.

The `yue-zhao` registry entry records the source and digest. The bilingual About bodies render this image inside the editor card, so it intentionally has no article-lead mapping. Keep their alt text and the Chinese media overlay consistent. The card links to the source homepage for photo credit and preserves the image's square aspect ratio.
