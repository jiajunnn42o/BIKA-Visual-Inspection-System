document.addEventListener(
    "DOMContentLoaded",
    () => {

        const page =
            document.querySelector(
                "[data-reports-page]"
            );

        if (!page) {
            return;
        }


        const initialJson =
            page.querySelector(
                "[data-reports-json]"
            );

        const data =
            JSON.parse(
                initialJson?.textContent
                ||
                "{}"
            );


        const state = {
            tab:
                "batches",

            batchPage:
                1,

            defectPage:
                1,

            pageSize:
                9,

            exportFields:
                (
                    data.export_fields
                    ||
                    []
                ).map(
                    (
                        field
                    ) =>
                        field.key
                ),
        };


        const batchBody =
            page.querySelector(
                "[data-batch-table-body]"
            );

        const defectBody =
            page.querySelector(
                "[data-defect-table-body]"
            );

        const detailModal =
            page.querySelector(
                "[data-reports-modal]"
            );

        const detailTitle =
            page.querySelector(
                "[data-detail-title]"
            );

        const detailKicker =
            page.querySelector(
                "[data-detail-kicker]"
            );

        const detailBody =
            page.querySelector(
                "[data-detail-body]"
            );

        const fieldsModal =
            page.querySelector(
                "[data-export-fields-modal]"
            );

        const fieldGrid =
            page.querySelector(
                "[data-export-field-grid]"
            );

        const rowExportModal =
            page.querySelector(
                "[data-row-export-modal]"
            );

        const rowExportName =
            page.querySelector(
                "[data-row-export-name]"
            );

        let pendingRowExport = null;
        let selectedRowExportFormats = new Set(["csv"]);
        let defectEventsLoading = true;


        const integerFormat =
            new Intl.NumberFormat(
                "en-US"
            );


        function escapeHtml(
            value
        ) {

            return String(
                value
                ??
                ""
            )
                .replaceAll(
                    "&",
                    "&amp;"
                )
                .replaceAll(
                    "<",
                    "&lt;"
                )
                .replaceAll(
                    ">",
                    "&gt;"
                )
                .replaceAll(
                    '"',
                    "&quot;"
                )
                .replaceAll(
                    "'",
                    "&#039;"
                );
        }


        function previewIcon(
            sourceType
        ) {

            const isVideo =
                String(sourceType).toLowerCase()
                ===
                "video";

            const label =
                isVideo
                    ? "Video"
                    : "Image";

            const iconName =
                isVideo
                    ? "video"
                    : "gallery";

            return `
                <span
                    class="reports-preview-icon reports-preview-symbol"
                    aria-label="${label}"
                    title="${label}"
                >
                    <iconsax-icon
                        name="${iconName}"
                        type="bold"
                        size="19"
                        color="currentColor"
                    ></iconsax-icon>
                </span>
            `;
        }

        const defectMeta = {
            too_dark: {
                label: "Too Dark",
                colour: "#D69A45",
            },
            too_short: {
                label: "Too Short",
                colour: "#8A69A8",
            },
            fractured: {
                label: "Fractured",
                colour: "#C65358",
            },
            bent_snack: {
                label: "Bent Snack",
                colour: "#6287B8",
            },
        };


        function probabilityPercent(
            value
        ) {
            const number =
                Number(value);

            if (!Number.isFinite(number)) {
                return 0;
            }

            return (
                number <= 1.00001
                    ? number * 100
                    : number
            );
        }


        function validBbox(
            bbox
        ) {
            if (!bbox) {
                return false;
            }

            return [
                bbox.x0,
                bbox.y0,
                bbox.x1,
                bbox.y1,
            ].every(
                (value) =>
                    Number.isFinite(
                        Number(value)
                    )
            );
        }


        async function loadIndividualDefectEvents() {
            const batches =
                data.batches
                ||
                [];

            const events = [];

            for (const batch of batches) {
                if (!batch.result_url) {
                    continue;
                }

                try {
                    const response =
                        await fetch(
                            batch.result_url,
                            {
                                credentials: "same-origin",
                                cache: "no-store",
                            }
                        );

                    if (!response.ok) {
                        throw new Error(
                            `Result JSON request failed: ${response.status}`
                        );
                    }

                    const result =
                        await response.json();

                    const objects =
                        Array.isArray(result?.objects)
                            ? result.objects
                            : [];

                    objects.forEach(
                        (object) => {
                            const classKey =
                                String(
                                    object?.class_name
                                    ||
                                    ""
                                );

                            if (
                                !object?.in_safe_zone
                                ||
                                classKey === "normal"
                                ||
                                !defectMeta[classKey]
                            ) {
                                return;
                            }

                            const meta =
                                defectMeta[classKey];

                            events.push(
                                {
                                    event_id:
                                        `${batch.batch_id}-${object.object_id}`,
                                    batch_id:
                                        batch.batch_id,
                                    object_id:
                                        object.object_id,
                                    review_id:
                                        object.review_id,
                                    file_name:
                                        batch.file_name,
                                    date_time:
                                        batch.date_time,
                                    date_display:
                                        batch.date_display,
                                    source_type:
                                        batch.source_type,
                                    preview_url:
                                        batch.preview_url,
                                    original_url:
                                        batch.original_url,
                                    annotated_url:
                                        batch.annotated_url,
                                    result_url:
                                        batch.result_url,
                                    class_key:
                                        classKey,
                                    class_name:
                                        object.display_name
                                        ||
                                        meta.label,
                                    colour:
                                        object.mask_colour
                                        ||
                                        meta.colour,
                                    class_confidence:
                                        probabilityPercent(
                                            object.class_confidence
                                        ),
                                    detection_confidence:
                                        probabilityPercent(
                                            object.detection_confidence
                                        ),
                                    bbox:
                                        validBbox(object.bbox)
                                            ? object.bbox
                                            : null,
                                    result_image_width:
                                        Number(
                                            result?.image?.width
                                            ||
                                            0
                                        ),
                                    result_image_height:
                                        Number(
                                            result?.image?.height
                                            ||
                                            0
                                        ),
                                    batch_status:
                                        batch.status,
                                    batch_status_key:
                                        batch.status_key,
                                    good_ratio:
                                        batch.good_ratio,
                                    model_version:
                                        batch.model_version,
                                }
                            );
                        }
                    );
                }
                catch (error) {
                    console.warn(
                        `Could not load defect objects for ${batch.batch_id}`,
                        error
                    );
                }
            }

            data.defect_events =
                events;

            defectEventsLoading = false;
            state.defectPage = 1;

            renderDefectTable();
        }


        function defectCropMedia(
            row
        ) {
            const originalUrl =
                row?.original_url
                ||
                row?.preview_url
                ||
                "";

            if (
                !originalUrl
                ||
                !validBbox(row?.bbox)
            ) {
                return detailMedia(row);
            }

            const annotatedUrl =
                row?.annotated_url
                ||
                "";

            const toggle =
                annotatedUrl
                    ? `
                        <button
                            type="button"
                            class="reports-detail-media-toggle"
                            data-defect-crop-toggle
                            data-event-id="${escapeHtml(row.event_id)}"
                            data-view="original"
                            aria-label="Switch to mask crop"
                        >
                            <iconsax-icon
                                name="layer"
                                type="twotone"
                                size="16"
                                color="currentColor"
                            ></iconsax-icon>

                            <span>Mask View</span>
                        </button>
                    `
                    : "";

            return `
                <div
                    class="reports-detail-media reports-defect-crop-media"
                    data-defect-crop-media
                    data-event-id="${escapeHtml(row.event_id)}"
                >
                    <canvas
                        class="reports-defect-crop-canvas"
                        data-defect-crop-canvas
                        aria-label="${escapeHtml(row.class_name)} crop"
                    ></canvas>

                    <div
                        class="reports-defect-crop-loading"
                        data-defect-crop-loading
                    >
                        Loading crop…
                    </div>

                    ${toggle}
                </div>
            `;
        }


        function drawDefectCrop(
            row,
            sourceUrl
        ) {
            if (
                !row
                ||
                !sourceUrl
                ||
                !validBbox(row.bbox)
            ) {
                return;
            }

            const container =
                detailBody?.querySelector(
                    `[data-defect-crop-media][data-event-id="${CSS.escape(row.event_id)}"]`
                );

            const canvas =
                container?.querySelector(
                    "[data-defect-crop-canvas]"
                );

            const loading =
                container?.querySelector(
                    "[data-defect-crop-loading]"
                );

            if (!canvas) {
                return;
            }

            if (loading) {
                loading.hidden = false;
            }

            const image =
                new Image();

            image.onload = () => {
                const bbox = row.bbox;

                const resultWidth =
                    Number(
                        row.result_image_width
                        ||
                        image.naturalWidth
                    );

                const resultHeight =
                    Number(
                        row.result_image_height
                        ||
                        image.naturalHeight
                    );

                const scaleX =
                    resultWidth
                        ? image.naturalWidth / resultWidth
                        : 1;

                const scaleY =
                    resultHeight
                        ? image.naturalHeight / resultHeight
                        : 1;

                /*
                 * result.json bbox coordinates refer to the
                 * original inference image. The stored source
                 * may have been resized to WebP after inference,
                 * so map coordinates into the stored image here.
                 */
                const x0 = Number(bbox.x0) * scaleX;
                const y0 = Number(bbox.y0) * scaleY;
                const x1 = Number(bbox.x1) * scaleX;
                const y1 = Number(bbox.y1) * scaleY;

                const boxWidth =
                    Math.max(
                        1,
                        x1 - x0
                    );

                const boxHeight =
                    Math.max(
                        1,
                        y1 - y0
                    );

                const padding =
                    Math.max(
                        10,
                        Math.round(
                            Math.max(
                                boxWidth,
                                boxHeight
                            )
                            *
                            0.28
                        )
                    );

                const cropX =
                    Math.max(
                        0,
                        Math.floor(
                            x0 - padding
                        )
                    );

                const cropY =
                    Math.max(
                        0,
                        Math.floor(
                            y0 - padding
                        )
                    );

                const cropRight =
                    Math.min(
                        image.naturalWidth,
                        Math.ceil(
                            x1 + padding
                        )
                    );

                const cropBottom =
                    Math.min(
                        image.naturalHeight,
                        Math.ceil(
                            y1 + padding
                        )
                    );

                const cropWidth =
                    Math.max(
                        1,
                        cropRight - cropX
                    );

                const cropHeight =
                    Math.max(
                        1,
                        cropBottom - cropY
                    );

                canvas.width = cropWidth;
                canvas.height = cropHeight;

                const context =
                    canvas.getContext(
                        "2d"
                    );

                context.clearRect(
                    0,
                    0,
                    cropWidth,
                    cropHeight
                );

                context.drawImage(
                    image,
                    cropX,
                    cropY,
                    cropWidth,
                    cropHeight,
                    0,
                    0,
                    cropWidth,
                    cropHeight
                );

                if (loading) {
                    loading.hidden = true;
                }
            };

            image.onerror = () => {
                if (loading) {
                    loading.textContent =
                        "Crop unavailable";
                }
            };

            image.src = sourceUrl;
        }


        function toggleDefectCrop(
            button
        ) {
            const row =
                findDefect(
                    button.dataset.eventId
                );

            if (!row) {
                return;
            }

            const currentView =
                button.dataset.view
                ||
                "original";

            const showMask =
                currentView
                ===
                "original";

            const nextUrl =
                showMask
                    ? row.annotated_url
                    : row.original_url;

            if (!nextUrl) {
                return;
            }

            drawDefectCrop(
                row,
                nextUrl
            );

            button.dataset.view =
                showMask
                    ? "mask"
                    : "original";

            const label =
                button.querySelector(
                    "span"
                );

            if (label) {
                label.textContent =
                    showMask
                        ? "Original"
                        : "Mask View";
            }
        }


        function detailMedia(
            row
        ) {

            const originalUrl =
                row?.original_url
                ||
                row?.preview_url
                ||
                "";

            const annotatedUrl =
                row?.annotated_url
                ||
                "";

            if (!originalUrl) {
                return "";
            }

            const fileName =
                row?.file_name
                ||
                "Inspection image";

            const toggle =
                annotatedUrl
                    ?
                    `
                        <button
                            type="button"
                            class="reports-detail-media-toggle"
                            data-detail-media-toggle
                            data-original-url="${escapeHtml(originalUrl)}"
                            data-annotated-url="${escapeHtml(annotatedUrl)}"
                            data-view="original"
                            aria-label="Switch to mask view"
                        >
                            <iconsax-icon
                                name="layer"
                                type="twotone"
                                size="16"
                                color="currentColor"
                            ></iconsax-icon>

                            <span>
                                Mask View
                            </span>
                        </button>
                    `
                    :
                    "";

            return `
                <div
                    class="reports-detail-media"
                    data-report-detail-media
                >
                    <img
                        src="${escapeHtml(originalUrl)}"
                        alt="${escapeHtml(fileName)}"
                        loading="lazy"
                        decoding="async"
                        data-detail-media-image
                    >

                    ${toggle}
                </div>
            `;
        }

        function detailButton(
            kind,
            id
        ) {

            return `
                <button
                    type="button"
                    class="reports-row-action"
                    data-detail-kind="${escapeHtml(kind)}"
                    data-detail-id="${escapeHtml(id)}"
                    aria-label="View details"
                >
                    <iconsax-icon
                        name="eye"
                        type="twotone"
                        size="17"
                        color="currentColor"
                    ></iconsax-icon>
                </button>
            `;
        }


        function rowExportButton(
            kind,
            id
        ) {

            return `
                <button
                    type="button"
                    class="reports-row-action"
                    data-row-export-kind="${escapeHtml(kind)}"
                    data-row-export-id="${escapeHtml(id)}"
                    aria-label="Export row"
                >
                    <iconsax-icon
                        name="export-arrow-01"
                        type="twotone"
                        size="19"
                        color="currentColor"
                    ></iconsax-icon>
                </button>
            `;
        }


        function statusBadge(
            label,
            key
        ) {

            return `
                <span class="reports-status reports-status-${escapeHtml(key)}">
                    ${escapeHtml(label)}
                </span>
            `;
        }


        function paginate(
            rows,
            pageNumber
        ) {

            const totalPages =
                Math.max(
                    1,
                    Math.ceil(
                        rows.length
                        /
                        state.pageSize
                    )
                );

            const page =
                Math.min(
                    Math.max(
                        1,
                        pageNumber
                    ),
                    totalPages
                );

            const start =
                (
                    page
                    -
                    1
                )
                *
                state.pageSize;

            return {
                page:
                    page,

                totalPages:
                    totalPages,

                start:
                    start,

                end:
                    Math.min(
                        rows.length,
                        start
                        +
                        state.pageSize
                    ),

                rows:
                    rows.slice(
                        start,
                        start
                        +
                        state.pageSize
                    ),
            };
        }


        function pageItems(
            currentPage,
            totalPages
        ) {

            if (totalPages <= 4) {
                return Array.from(
                    { length: totalPages },
                    (_, index) => index + 1
                );
            }

            if (currentPage <= 3) {
                return [
                    1,
                    2,
                    3,
                    "…",
                    totalPages,
                ];
            }

            if (
                currentPage
                >=
                totalPages - 2
            ) {
                return [
                    1,
                    "…",
                    totalPages - 2,
                    totalPages - 1,
                    totalPages,
                ];
            }

            return [
                1,
                "…",
                currentPage,
                "…",
                totalPages,
            ];
        }


        function renderPageButtons(
            selector,
            kind,
            currentPage,
            totalPages
        ) {

            const container =
                page.querySelector(
                    selector
                );

            if (!container) {
                return;
            }

            container.innerHTML =
                pageItems(
                    currentPage,
                    totalPages
                )
                .map(
                    (item) => {

                        if (item === "…") {
                            return `
                                <span
                                    class="reports-page-ellipsis"
                                    aria-hidden="true"
                                >…</span>
                            `;
                        }

                        const active =
                            Number(item)
                            ===
                            Number(currentPage);

                        return `
                            <button
                                type="button"
                                class="reports-page-button${active ? " is-active" : ""}"
                                data-page-kind="${kind}"
                                data-page-target="${item}"
                                aria-label="Go to page ${item}"
                                ${active ? 'aria-current="page"' : ""}
                            >
                                ${item}
                            </button>
                        `;
                    }
                )
                .join("");
        }


        function renderBatchTable() {

            const rows =
                data.batches
                ||
                [];

            const result =
                paginate(
                    rows,
                    state.batchPage
                );

            state.batchPage =
                result.page;

            if (batchBody) {

                batchBody.innerHTML =
                    result.rows
                    .map(
                        (
                            row
                        ) => `
                            <tr>
                                <td>
                                    ${previewIcon(row.source_type)}
                                </td>

                                <td>
                                    <span
                                        class="reports-file-name"
                                        title="${escapeHtml(row.file_name)}"
                                    >
                                        ${escapeHtml(row.file_name)}
                                    </span>
                                </td>

                                <td>
                                    ${escapeHtml(row.date_display)}
                                </td>

                                <td class="reports-ratio">
                                    ${integerFormat.format(row.total)}
                                </td>

                                <td class="reports-good">
                                    ${integerFormat.format(row.good)}
                                </td>

                                <td class="reports-bad">
                                    ${integerFormat.format(row.bad)}
                                </td>

                                <td class="reports-ratio">
                                    ${Number(row.good_ratio).toFixed(1)}%
                                </td>

                                <td>
                                    ${statusBadge(
                                        row.status,
                                        row.status_key
                                    )}
                                </td>

                                <td>
                                    ${detailButton(
                                        "batch",
                                        row.batch_id
                                    )}
                                </td>

                                <td>
                                    ${rowExportButton(
                                        "batch",
                                        row.batch_id
                                    )}
                                </td>
                            </tr>
                        `
                    )
                    .join("");
            }


            setText(
                "[data-batch-page-summary]",
                rows.length
                    ?
                    (
                        `Showing ${result.start + 1} – ${result.end} of ${rows.length} runs`
                    )
                    :
                    "No inspection runs"
            );

            renderPageButtons(
                "[data-batch-page-buttons]",
                "batch",
                result.page,
                result.totalPages
            );


            const prev =
                page.querySelector(
                    "[data-batch-prev]"
                );

            const next =
                page.querySelector(
                    "[data-batch-next]"
                );

            if (prev) {
                prev.disabled =
                    result.page
                    <=
                    1;
            }

            if (next) {
                next.disabled =
                    result.page
                    >=
                    result.totalPages;
            }
        }


        function renderDefectTable() {

            const rows =
                data.defect_events
                ||
                [];

            const result =
                paginate(
                    rows,
                    state.defectPage
                );

            state.defectPage =
                result.page;

            if (defectBody) {

                defectBody.innerHTML =
                    defectEventsLoading
                        ? `
                            <tr>
                                <td
                                    colspan="9"
                                    class="reports-defect-loading"
                                >
                                    Loading defect events…
                                </td>
                            </tr>
                        `
                        : result.rows
                    .map(
                        (
                            row
                        ) => `
                            <tr>
                                <td>
                                    ${previewIcon(row.source_type)}
                                </td>

                                <td>
                                    <strong class="reports-object-id">
                                        ${escapeHtml(row.object_id)}
                                    </strong>
                                </td>

                                <td>
                                    <span
                                        class="reports-file-name"
                                        title="${escapeHtml(row.file_name)}"
                                    >
                                        ${escapeHtml(row.file_name)}
                                    </span>
                                </td>

                                <td>
                                    ${escapeHtml(row.date_display)}
                                </td>

                                <td>
                                    <span class="reports-defect-label">
                                        <span
                                            class="reports-defect-dot"
                                            style="--defect-colour:${escapeHtml(row.colour)}"
                                        ></span>

                                        ${escapeHtml(row.class_name)}
                                    </span>
                                </td>

                                <td class="reports-ratio">
                                    ${Number(row.class_confidence).toFixed(1)}%
                                </td>

                                <td class="reports-ratio">
                                    ${Number(row.detection_confidence).toFixed(1)}%
                                </td>

                                <td>
                                    ${detailButton(
                                        "defect",
                                        row.event_id
                                    )}
                                </td>

                                <td>
                                    ${rowExportButton(
                                        "defect",
                                        row.event_id
                                    )}
                                </td>
                            </tr>
                        `
                    )
                    .join("");
            }


            setText(
                "[data-defect-page-summary]",
                defectEventsLoading
                    ?
                    "Loading defect events…"
                    : rows.length
                        ?
                        (
                            `Showing ${result.start + 1} – ${result.end} of ${rows.length} defect events`
                        )
                        :
                        "No defect events"
            );

            renderPageButtons(
                "[data-defect-page-buttons]",
                "defect",
                result.page,
                result.totalPages
            );


            const prev =
                page.querySelector(
                    "[data-defect-prev]"
                );

            const next =
                page.querySelector(
                    "[data-defect-next]"
                );

            if (prev) {
                prev.disabled =
                    result.page
                    <=
                    1;
            }

            if (next) {
                next.disabled =
                    result.page
                    >=
                    result.totalPages;
            }
        }


        function setText(
            selector,
            value
        ) {

            const element =
                page.querySelector(
                    selector
                );

            if (element) {
                element.textContent =
                    value;
            }
        }


        function setTab(
            tab
        ) {

            state.tab =
                tab;

            page
                .querySelectorAll(
                    "[data-report-tab]"
                )
                .forEach(
                    (
                        button
                    ) => {

                        const active =
                            (
                                button.dataset.reportTab
                                ===
                                tab
                            );

                        button.classList.toggle(
                            "is-active",
                            active
                        );

                        button.setAttribute(
                            "aria-selected",
                            active
                                ?
                                "true"
                                :
                                "false"
                        );
                    }
                );


            page
                .querySelectorAll(
                    "[data-report-panel]"
                )
                .forEach(
                    (
                        panel
                    ) => {

                        panel.hidden =
                            (
                                panel.dataset.reportPanel
                                !==
                                tab
                            );
                    }
                );
        }


        function findBatch(
            batchId
        ) {

            return (
                data.batches
                ||
                []
            ).find(
                (
                    row
                ) =>
                    row.batch_id
                    ===
                    batchId
            );
        }


        function findDefect(
            eventId
        ) {

            return (
                data.defect_events
                ||
                []
            ).find(
                (
                    row
                ) =>
                    row.event_id
                    ===
                    eventId
            );
        }


        function openDetail(
            kind,
            id
        ) {

            if (!detailModal) {
                return;
            }


            if (
                kind
                ===
                "batch"
            ) {

                const row =
                    findBatch(
                        id
                    );

                if (!row) {
                    return;
                }

                detailKicker.textContent =
                    row.batch_id;

                detailTitle.textContent =
                    row.file_name;

                const classItems =
                    (
                        row.classes
                        ||
                        []
                    );

                const inspectedTotal =
                    Number(row.total)
                    ||
                    classItems.reduce(
                        (sum, item) =>
                            sum
                            +
                            Number(item.count || 0),
                        0
                    );

                const classBar =
                    classItems
                    .filter(
                        (item) =>
                            Number(item.count || 0)
                            >
                            0
                    )
                    .map(
                        (item) => {

                            const percentage =
                                inspectedTotal
                                    ?
                                    (
                                        Number(item.count || 0)
                                        /
                                        inspectedTotal
                                        *
                                        100
                                    )
                                    :
                                    0;

                            return `
                                <span
                                    class="reports-reason-segment"
                                    style="
                                        --reason-colour:${escapeHtml(item.colour)};
                                        --reason-width:${percentage.toFixed(4)}%;
                                    "
                                    title="${escapeHtml(item.label)}: ${percentage.toFixed(1)}%"
                                ></span>
                            `;
                        }
                    )
                    .join("");

                const classRows =
                    classItems
                    .map(
                        (item) => {

                            const count =
                                Number(item.count || 0);

                            const percentage =
                                inspectedTotal
                                    ?
                                    (
                                        count
                                        /
                                        inspectedTotal
                                        *
                                        100
                                    )
                                    :
                                    0;

                            return `
                                <div class="reports-reason-row">

                                    <span
                                        class="reports-defect-dot"
                                        style="--defect-colour:${escapeHtml(item.colour)}"
                                    ></span>

                                    <span class="reports-reason-label">
                                        ${escapeHtml(item.label)}
                                    </span>

                                    <strong class="reports-reason-count">
                                        ${integerFormat.format(count)}
                                    </strong>

                                    <span class="reports-reason-percent">
                                        ${percentage.toFixed(1)}%
                                    </span>

                                </div>
                            `;
                        }
                    )
                    .join("");


                detailBody.innerHTML = `
                    ${detailMedia(row)}

                    <section class="reports-reason-breakdown">

                        <h3 class="reports-detail-section-title">
                            Reason Breakdown
                        </h3>

                        <div class="reports-reason-summary">
                            <strong>
                                ${integerFormat.format(inspectedTotal)}
                            </strong>
                            <span>products inspected</span>
                        </div>

                        <div
                            class="reports-reason-bar"
                            aria-label="Inspection class distribution"
                        >
                            ${classBar}
                        </div>

                        <div class="reports-reason-legend">
                            ${classRows}
                        </div>

                    </section>

                    <div class="reports-detail-grid">

                        ${detailItem(
                            "Source Type",
                            row.source_type === "video"
                                ? "Video"
                                : "Image"
                        )}

                        ${detailItem(
                            "Model Version",
                            row.model_version
                        )}

                        ${detailItem(
                            "Detection Confidence",
                            `${Number(row.average_detection_confidence).toFixed(1)}%`
                        )}

                        ${detailItem(
                            "Class Confidence",
                            `${Number(row.average_class_confidence).toFixed(1)}%`
                        )}

                        ${detailItem(
                            "Detected Boxes",
                            integerFormat.format(row.detected_boxes)
                        )}

                        ${detailItem(
                            "SAM2 Masks",
                            integerFormat.format(row.sam2_masks)
                        )}

                        ${detailItem(
                            "Edge Not Judged",
                            integerFormat.format(row.edge_not_judged)
                        )}

                        ${detailItem(
                            "Runtime",
                            `${Number(row.total_runtime_seconds).toFixed(1)} s`
                        )}

                    </div>
                `;
            }

            else {

                const row =
                    findDefect(
                        id
                    );

                if (!row) {
                    return;
                }

                detailKicker.textContent =
                    row.batch_id;

                detailTitle.textContent =
                    row.class_name;

                detailBody.innerHTML = `
                    ${defectCropMedia(row)}

                    <div class="reports-detail-grid reports-detail-grid-compact">

                        ${detailItem(
                            "Object ID",
                            row.object_id
                        )}

                        ${detailItem(
                            "Model Version",
                            row.model_version
                        )}

                        ${detailItem(
                            "Class Confidence",
                            `${Number(row.class_confidence).toFixed(1)}%`
                        )}

                        ${detailItem(
                            "Detection Confidence",
                            `${Number(row.detection_confidence).toFixed(1)}%`
                        )}

                    </div>
                `;

                drawDefectCrop(
                    row,
                    row.original_url
                    ||
                    row.preview_url
                );
            }


            detailModal.hidden =
                false;

            document.body.style.overflow =
                "hidden";
        }


        function detailItem(
            label,
            value
        ) {

            return `
                <div class="reports-detail-item">

                    <small>
                        ${escapeHtml(label)}
                    </small>

                    <strong>
                        ${escapeHtml(value)}
                    </strong>

                </div>
            `;
        }


        function toggleDetailMedia(
            button
        ) {

            const container =
                button.closest(
                    "[data-report-detail-media]"
                );

            const image =
                container?.querySelector(
                    "[data-detail-media-image]"
                );

            if (!image) {
                return;
            }

            const currentView =
                button.dataset.view
                ||
                "original";

            const showMask =
                currentView
                ===
                "original";

            const nextUrl =
                showMask
                    ?
                    button.dataset.annotatedUrl
                    :
                    button.dataset.originalUrl;

            if (!nextUrl) {
                return;
            }

            image.src =
                nextUrl;

            button.dataset.view =
                showMask
                    ?
                    "mask"
                    :
                    "original";

            button.setAttribute(
                "aria-label",
                showMask
                    ?
                    "Switch to original image"
                    :
                    "Switch to mask view"
            );

            const label =
                button.querySelector(
                    "span"
                );

            if (label) {
                label.textContent =
                    showMask
                        ?
                        "Original"
                        :
                        "Mask View";
            }
        }


        function closeDetail() {

            if (!detailModal) {
                return;
            }

            detailModal.hidden =
                true;

            document.body.style.overflow =
                "";
        }


        function openFields() {

            if (
                !fieldsModal
                ||
                !fieldGrid
            ) {
                return;
            }


            fieldGrid.innerHTML =
                (
                    data.export_fields
                    ||
                    []
                )
                .map(
                    (
                        field
                    ) => {

                        const checked =
                            state.exportFields.includes(
                                field.key
                            );

                        return `
                            <label class="reports-field-option">

                                <input
                                    type="checkbox"
                                    value="${escapeHtml(field.key)}"
                                    ${checked ? "checked" : ""}
                                    data-export-field
                                >

                                <span>
                                    ${escapeHtml(field.label)}
                                </span>

                            </label>
                        `;
                    }
                )
                .join("");


            fieldsModal.hidden =
                false;

            document.body.style.overflow =
                "hidden";
        }


        function closeFields() {

            if (!fieldsModal) {
                return;
            }

            fieldsModal.hidden =
                true;

            document.body.style.overflow =
                "";
        }


        function saveFields() {

            const checked =
                [
                    ...page.querySelectorAll(
                        "[data-export-field]:checked"
                    )
                ]
                .map(
                    (
                        input
                    ) =>
                        input.value
                );


            if (!checked.length) {
                return;
            }


            state.exportFields =
                checked;

            closeFields();
        }


        function selectAllFields() {

            page
                .querySelectorAll(
                    "[data-export-field]"
                )
                .forEach(
                    (
                        input
                    ) => {
                        input.checked =
                            true;
                    }
                );
        }


        function exportRows(
            format
        ) {

            const rows =
                state.tab
                ===
                "defects"
                ?
                (
                    data.defect_events
                    ||
                    []
                )
                :
                (
                    data.batches
                    ||
                    []
                );


            if (
                state.tab
                ===
                "defects"
            ) {

                const fields = [
                    "batch_id",
                    "file_name",
                    "date_display",
                    "class_name",
                    "count",
                    "ratio",
                    "good_ratio",
                    "batch_status",
                    "model_version",
                ];

                downloadData(
                    rows,
                    fields,
                    format,
                    "bika_defect_event_log"
                );

                return;
            }


            downloadData(
                rows,
                state.exportFields,
                format,
                "bika_batch_summary"
            );
        }


        function updateRowExportFormatUI() {

            page
                .querySelectorAll(
                    "[data-row-export-format]"
                )
                .forEach(
                    (
                        button
                    ) => {

                        const selected =
                            selectedRowExportFormats.has(
                                button.dataset.rowExportFormat
                            );

                        button.classList.toggle(
                            "is-selected",
                            selected
                        );

                        button.setAttribute(
                            "aria-checked",
                            selected
                                ?
                                "true"
                                :
                                "false"
                        );
                    }
                );

            const confirmButton =
                page.querySelector(
                    "[data-row-export-confirm]"
                );

            if (confirmButton) {
                confirmButton.disabled =
                    selectedRowExportFormats.size === 0;
            }
        }


        function toggleRowExportFormat(
            format
        ) {

            const normalizedFormat =
                format === "json"
                    ?
                    "json"
                    :
                    "csv";

            if (
                selectedRowExportFormats.has(
                    normalizedFormat
                )
            ) {
                selectedRowExportFormats.delete(
                    normalizedFormat
                );
            } else {
                selectedRowExportFormats.add(
                    normalizedFormat
                );
            }

            updateRowExportFormatUI();
        }


        function openRowExportModal(
            kind,
            id
        ) {

            const row =
                kind
                ===
                "batch"
                ?
                findBatch(
                    id
                )
                :
                findDefect(
                    id
                );

            if (
                !row
                ||
                !rowExportModal
            ) {
                return;
            }

            pendingRowExport = {
                kind,
                id,
            };

            if (rowExportName) {
                rowExportName.textContent =
                    kind
                    ===
                    "batch"
                    ?
                    (row.batch_id || "Selected batch")
                    :
                    (row.event_id || "Selected event");
            }

            selectedRowExportFormats =
                new Set([
                    "csv",
                ]);

            updateRowExportFormatUI();

            rowExportModal.hidden = false;
        }


        function closeRowExportModal() {

            if (rowExportModal) {
                rowExportModal.hidden = true;
            }

            pendingRowExport = null;
        }


        function exportSingleRow(
            kind,
            id,
            format
        ) {

            const row =
                kind
                ===
                "batch"
                ?
                findBatch(
                    id
                )
                :
                findDefect(
                    id
                );


            if (!row) {
                return;
            }

            const baseName =
                kind
                ===
                "batch"
                ?
                (row.batch_id || "bika_batch")
                :
                (row.event_id || "bika_defect_event");

            if (
                format
                ===
                "csv"
            ) {

                const fields =
                    Object.keys(
                        row
                    );

                const csvRow = {};

                fields.forEach(
                    (
                        field
                    ) => {

                        const value =
                            row[field];

                        csvRow[field] =
                            (
                                value
                                !==
                                null
                                &&
                                typeof value
                                ===
                                "object"
                            )
                                ?
                                JSON.stringify(
                                    value
                                )
                                :
                                value;
                    }
                );

                downloadData(
                    [csvRow],
                    fields,
                    "csv",
                    baseName
                );

                return;
            }


            downloadBlob(
                JSON.stringify(
                    row,
                    null,
                    2
                ),
                `${baseName}.json`,
                "application/json;charset=utf-8"
            );
        }


        function downloadData(
            rows,
            fields,
            format,
            baseName
        ) {

            if (
                format
                ===
                "json"
            ) {

                const output =
                    rows.map(
                        (
                            row
                        ) => {

                            const selected = {};

                            fields.forEach(
                                (
                                    field
                                ) => {
                                    selected[field] =
                                        row[field];
                                }
                            );

                            return selected;
                        }
                    );


                downloadBlob(
                    JSON.stringify(
                        output,
                        null,
                        2
                    ),
                    `${baseName}.json`,
                    "application/json;charset=utf-8"
                );

                return;
            }


            const csv =
                toCsv(
                    rows,
                    fields
                );


            downloadBlob(
                csv,
                `${baseName}.csv`,
                "text/csv;charset=utf-8"
            );
        }


        function toCsv(
            rows,
            fields
        ) {

            const labels =
                Object.fromEntries(
                    (
                        data.export_fields
                        ||
                        []
                    ).map(
                        (
                            field
                        ) => [
                            field.key,
                            field.label,
                        ]
                    )
                );


            const header =
                fields.map(
                    (
                        field
                    ) =>
                        csvCell(
                            labels[field]
                            ||
                            humanize(
                                field
                            )
                        )
                );


            const body =
                rows.map(
                    (
                        row
                    ) =>
                        fields.map(
                            (
                                field
                            ) =>
                                csvCell(
                                    row[field]
                                )
                        )
                );


            return [
                header,
                ...body,
            ]
                .map(
                    (
                        row
                    ) =>
                        row.join(",")
                )
                .join("\r\n");
        }


        function humanize(
            value
        ) {

            return String(
                value
            )
                .replaceAll(
                    "_",
                    " "
                )
                .replace(
                    /\b\w/g,
                    (
                        letter
                    ) =>
                        letter.toUpperCase()
                );
        }


        function csvCell(
            value
        ) {

            const text =
                String(
                    value
                    ??
                    ""
                );

            return (
                '"'
                +
                text.replaceAll(
                    '"',
                    '""'
                )
                +
                '"'
            );
        }


        function downloadBlob(
            content,
            fileName,
            type
        ) {

            const blob =
                new Blob(
                    [
                        content,
                    ],
                    {
                        type:
                            type,
                    }
                );

            const url =
                URL.createObjectURL(
                    blob
                );

            const anchor =
                document.createElement(
                    "a"
                );

            anchor.href =
                url;

            anchor.download =
                fileName;

            document.body.appendChild(
                anchor
            );

            anchor.click();

            anchor.remove();

            URL.revokeObjectURL(
                url
            );
        }


        page
            .querySelectorAll(
                "[data-report-tab]"
            )
            .forEach(
                (
                    button
                ) => {

                    button.addEventListener(
                        "click",
                        () => {

                            setTab(
                                button.dataset.reportTab
                            );
                        }
                    );
                }
            );


        page
            .querySelector(
                "[data-batch-prev]"
            )
            ?.addEventListener(
                "click",
                () => {

                    state.batchPage -=
                        1;

                    renderBatchTable();
                }
            );


        page
            .querySelector(
                "[data-batch-next]"
            )
            ?.addEventListener(
                "click",
                () => {

                    state.batchPage +=
                        1;

                    renderBatchTable();
                }
            );


        page
            .querySelector(
                "[data-defect-prev]"
            )
            ?.addEventListener(
                "click",
                () => {

                    state.defectPage -=
                        1;

                    renderDefectTable();
                }
            );


        page
            .querySelector(
                "[data-defect-next]"
            )
            ?.addEventListener(
                "click",
                () => {

                    state.defectPage +=
                        1;

                    renderDefectTable();
                }
            );


        page.addEventListener(
            "click",
            (
                event
            ) => {

                const pageButton =
                    event.target.closest(
                        "[data-page-target]"
                    );

                if (pageButton) {

                    const targetPage =
                        Number(
                            pageButton.dataset.pageTarget
                        );

                    if (
                        Number.isFinite(targetPage)
                        &&
                        targetPage > 0
                    ) {

                        if (
                            pageButton.dataset.pageKind
                            ===
                            "batch"
                        ) {
                            state.batchPage =
                                targetPage;

                            renderBatchTable();
                        }
                        else {
                            state.defectPage =
                                targetPage;

                            renderDefectTable();
                        }
                    }

                    return;
                }


                const defectCropToggle =
                    event.target.closest(
                        "[data-defect-crop-toggle]"
                    );

                if (defectCropToggle) {

                    toggleDefectCrop(
                        defectCropToggle
                    );

                    return;
                }


                const mediaToggle =
                    event.target.closest(
                        "[data-detail-media-toggle]"
                    );

                if (mediaToggle) {

                    toggleDetailMedia(
                        mediaToggle
                    );

                    return;
                }


                const detailButton =
                    event.target.closest(
                        "[data-detail-kind]"
                    );

                if (detailButton) {

                    openDetail(
                        detailButton.dataset.detailKind,
                        detailButton.dataset.detailId
                    );

                    return;
                }


                const rowExport =
                    event.target.closest(
                        "[data-row-export-kind]"
                    );

                if (rowExport) {

                    openRowExportModal(
                        rowExport.dataset.rowExportKind,
                        rowExport.dataset.rowExportId
                    );
                }
            }
        );


        page
            .querySelector(
                "[data-reports-modal-close]"
            )
            ?.addEventListener(
                "click",
                closeDetail
            );


        detailModal
            ?.addEventListener(
                "click",
                (
                    event
                ) => {

                    if (
                        event.target
                        ===
                        detailModal
                    ) {
                        closeDetail();
                    }
                }
            );


        page
            .querySelector(
                "[data-export-fields-button]"
            )
            ?.addEventListener(
                "click",
                openFields
            );


        page
            .querySelector(
                "[data-export-fields-close]"
            )
            ?.addEventListener(
                "click",
                closeFields
            );


        page
            .querySelector(
                "[data-export-fields-save]"
            )
            ?.addEventListener(
                "click",
                saveFields
            );


        page
            .querySelector(
                "[data-export-select-all]"
            )
            ?.addEventListener(
                "click",
                selectAllFields
            );


        fieldsModal
            ?.addEventListener(
                "click",
                (
                    event
                ) => {

                    if (
                        event.target
                        ===
                        fieldsModal
                    ) {
                        closeFields();
                    }
                }
            );


        page
            .querySelector(
                "[data-row-export-close]"
            )
            ?.addEventListener(
                "click",
                closeRowExportModal
            );


        rowExportModal
            ?.addEventListener(
                "click",
                (
                    event
                ) => {

                    if (
                        event.target
                        ===
                        rowExportModal
                    ) {
                        closeRowExportModal();
                    }
                }
            );


        page
            .querySelectorAll(
                "[data-row-export-format]"
            )
            .forEach(
                (
                    button
                ) => {

                    button.addEventListener(
                        "click",
                        () => {
                            toggleRowExportFormat(
                                button.dataset.rowExportFormat
                            );
                        }
                    );
                }
            );


        page
            .querySelector(
                "[data-row-export-cancel]"
            )
            ?.addEventListener(
                "click",
                closeRowExportModal
            );


        page
            .querySelector(
                "[data-row-export-confirm]"
            )
            ?.addEventListener(
                "click",
                () => {

                    if (!pendingRowExport) {
                        return;
                    }

                    if (
                        selectedRowExportFormats.size
                        ===
                        0
                    ) {
                        return;
                    }

                    const exportTarget = {
                        ...pendingRowExport,
                    };

                    const formats =
                        Array.from(
                            selectedRowExportFormats
                        );

                    formats.forEach(
                        (
                            format,
                            index
                        ) => {

                            window.setTimeout(
                                () => {
                                    exportSingleRow(
                                        exportTarget.kind,
                                        exportTarget.id,
                                        format
                                    );
                                },
                                index * 120
                            );
                        }
                    );

                    closeRowExportModal();
                }
            );


        page
            .querySelectorAll(
                "[data-download-format]"
            )
            .forEach(
                (
                    button
                ) => {

                    button.addEventListener(
                        "click",
                        () => {

                            exportRows(
                                button.dataset.downloadFormat
                            );
                        }
                    );
                }
            );


        document.addEventListener(
            "keydown",
            (
                event
            ) => {

                if (
                    event.key
                    !==
                    "Escape"
                ) {
                    return;
                }

                closeDetail();
                closeFields();
                closeRowExportModal();
            }
        );


        renderBatchTable();

        /*
         * Defect Event Log is built from result.json objects,
         * so every defective biscuit becomes one real event.
         */
        data.defect_events = [];
        renderDefectTable();
        loadIndividualDefectEvents();

        setTab(
            "batches"
        );

    }
);
