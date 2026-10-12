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

            const icon =
                isVideo
                    ?
                    `
                        <svg
                            class="reports-preview-glyph"
                            viewBox="0 0 24 24"
                            fill="none"
                            aria-hidden="true"
                        >
                            <rect
                                x="4"
                                y="6"
                                width="11"
                                height="12"
                                rx="2.5"
                            ></rect>
                            <path
                                d="M15 10L20 7.5V16.5L15 14"
                            ></path>
                        </svg>
                    `
                    :
                    `
                        <svg
                            class="reports-preview-glyph"
                            viewBox="0 0 24 24"
                            fill="none"
                            aria-hidden="true"
                        >
                            <rect
                                x="4"
                                y="4"
                                width="16"
                                height="16"
                                rx="3"
                            ></rect>
                            <circle
                                cx="9"
                                cy="9"
                                r="1.5"
                            ></circle>
                            <path
                                d="M6.5 17L11 12.5L14 15.5L16.5 13L19 15.5"
                            ></path>
                        </svg>
                    `;

            return `
                <span
                    class="reports-preview-icon reports-preview-symbol"
                    aria-label="${label}"
                    title="${label}"
                >
                    ${icon}
                </span>
            `;
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
                        size="16"
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
                    <svg
                        class="reports-export-icon"
                        viewBox="0 0 24 24"
                        fill="none"
                        aria-hidden="true"
                    >
                        <path
                            d="M12 15V3"
                        ></path>
                        <path
                            d="M7.5 7.5L12 3L16.5 7.5"
                        ></path>
                        <path
                            d="M5.5 10.5H4.75C3.23 10.5 2 11.73 2 13.25V18.25C2 19.77 3.23 21 4.75 21H19.25C20.77 21 22 19.77 22 18.25V13.25C22 11.73 20.77 10.5 19.25 10.5H18.5"
                        ></path>
                    </svg>
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
                        `Showing ${result.start + 1}–${result.end} of ${rows.length} runs`
                    )
                    :
                    "No inspection runs"
            );

            setText(
                "[data-batch-page-number]",
                `${result.page} / ${result.totalPages}`
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

                                <td>
                                    <span class="reports-defect-label">
                                        <span
                                            class="reports-defect-dot"
                                            style="--defect-colour:${escapeHtml(row.colour)}"
                                        ></span>

                                        ${escapeHtml(row.class_name)}
                                    </span>
                                </td>

                                <td class="reports-bad">
                                    ${integerFormat.format(row.count)}
                                </td>

                                <td class="reports-ratio">
                                    ${Number(row.ratio).toFixed(1)}%
                                </td>

                                <td>
                                    ${statusBadge(
                                        row.batch_status,
                                        row.batch_status_key
                                    )}
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
                rows.length
                    ?
                    (
                        `Showing ${result.start + 1}–${result.end} of ${rows.length} defect groups`
                    )
                    :
                    "No defect events"
            );

            setText(
                "[data-defect-page-number]",
                `${result.page} / ${result.totalPages}`
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

                const classRows =
                    (
                        row.classes
                        ||
                        []
                    )
                    .map(
                        (
                            item
                        ) => `
                            <div class="reports-class-breakdown-row">

                                <span
                                    class="reports-defect-dot"
                                    style="--defect-colour:${escapeHtml(item.colour)}"
                                ></span>

                                <span>
                                    ${escapeHtml(item.label)}
                                </span>

                                <strong>
                                    ${integerFormat.format(item.count)}
                                </strong>

                            </div>
                        `
                    )
                    .join("");


                detailBody.innerHTML = `
                    ${detailMedia(row)}

                    <div class="reports-detail-grid">

                        ${detailItem(
                            "Date / Time",
                            row.date_display
                        )}

                        ${detailItem(
                            "Source Type",
                            row.source_type === "video"
                                ? "Video"
                                : "Image"
                        )}

                        ${detailItem(
                            "Products Judged",
                            integerFormat.format(row.total)
                        )}

                        ${detailItem(
                            "Good Ratio",
                            `${Number(row.good_ratio).toFixed(1)}%`
                        )}

                        ${detailItem(
                            "Status",
                            row.status
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

                    <h3 class="reports-detail-section-title">
                        Class Breakdown
                    </h3>

                    <div class="reports-class-breakdown">
                        ${classRows}
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
                    ${detailMedia(row)}

                    <div class="reports-detail-grid">

                        ${detailItem(
                            "File Name",
                            row.file_name
                        )}

                        ${detailItem(
                            "Date / Time",
                            row.date_display
                        )}

                        ${detailItem(
                            "Defect Class",
                            row.class_name
                        )}

                        ${detailItem(
                            "Defect Count",
                            integerFormat.format(row.count)
                        )}

                        ${detailItem(
                            "Share of Batch",
                            `${Number(row.ratio).toFixed(1)}%`
                        )}

                        ${detailItem(
                            "Good Ratio",
                            `${Number(row.good_ratio).toFixed(1)}%`
                        )}

                        ${detailItem(
                            "Batch Status",
                            row.batch_status
                        )}

                        ${detailItem(
                            "Model Version",
                            row.model_version
                        )}

                    </div>
                `;
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


        function exportSingleRow(
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


            if (!row) {
                return;
            }


            downloadBlob(
                JSON.stringify(
                    row,
                    null,
                    2
                ),
                (
                    kind
                    ===
                    "batch"
                    ?
                    `${row.batch_id}.json`
                    :
                    `${row.event_id}.json`
                ),
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

                    exportSingleRow(
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
            }
        );


        renderBatchTable();
        renderDefectTable();
        setTab(
            "batches"
        );

    }
);
