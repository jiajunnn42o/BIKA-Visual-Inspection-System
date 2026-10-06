(() => {

    "use strict";


    /* =====================================================
       PAGE
       ===================================================== */

    const page =
        document.querySelector(
            "[data-system-page]"
        );


    if (!page) {
        return;
    }


    /* =====================================================
       TABLE ELEMENTS
       ===================================================== */

    const tableBody =
        page.querySelector(
            "[data-system-table-body]"
        );


    const rows =
        Array.from(
            page.querySelectorAll(
                "[data-system-user-row]"
            )
        );


    const search =
        page.querySelector(
            "[data-system-search]"
        );


    const roleFilter =
        page.querySelector(
            "[data-system-role-filter]"
        );


    const statusFilter =
        page.querySelector(
            "[data-system-status-filter]"
        );


    const securityFilter =
        page.querySelector(
            "[data-system-security-filter]"
        );


    const prevButton =
        page.querySelector(
            "[data-system-prev]"
        );


    const nextButton =
        page.querySelector(
            "[data-system-next]"
        );


    const pageNumbers =
        page.querySelector(
            "[data-system-page-numbers]"
        );


    const resultText =
        page.querySelector(
            "[data-system-result-text]"
        );


    const exportButton =
        page.querySelector(
            "[data-system-export]"
        );


    /* =====================================================
       PAGINATION
       ===================================================== */

    const perPage = 5;

    let currentPage = 1;


    /* =====================================================
       SORT
       Same flow as Registration Requests
       ===================================================== */

    const sortButtons =
        Array.from(
            page.querySelectorAll(
                "[data-system-sort-key]"
            )
        );


    let activeSortKey = null;

    let activeSortDirection = null;


    /* =====================================================
       CURRENT PROCESSED ROWS
       ===================================================== */

    let processedRows = [
        ...rows
    ];


    /* =====================================================
       NORMALIZE
       ===================================================== */

    function normalize(
        value
    ) {

        return String(
            value ?? ""
        )
            .trim()
            .toLowerCase();

    }


    /* =====================================================
       SORT VALUE
       ===================================================== */

    function getSortValue(
        row,
        key
    ) {

        const map = {

            user:
                "sortUser",

            role:
                "sortRole",

            status:
                "sortStatus",

            last_active:
                "sortLastActive",

            last_login:
                "sortLastLogin",

            security:
                "sortSecurity"

        };


        const datasetKey =
            map[key];


        if (!datasetKey) {
            return "";
        }


        return (
            row.dataset[
                datasetKey
            ]
            ??
            ""
        );

    }


    /* =====================================================
       DATE VALUE
       ===================================================== */

    function getDateValue(
        value
    ) {

        const text =
            String(
                value ?? ""
            )
                .trim();


        if (
            !text
            ||
            text === "—"
            ||
            text === "-"
        ) {
            return 0;
        }


        const normalized =
            text.includes("T")
                ? text
                : text.replace(
                    " ",
                    "T"
                );


        const timestamp =
            Date.parse(
                normalized
            );


        return Number.isNaN(
            timestamp
        )
            ? 0
            : timestamp;

    }


    /* =====================================================
       COMPARE ROWS
       ===================================================== */

    function compareRows(
        rowA,
        rowB,
        key,
        direction
    ) {

        const valueA =
            getSortValue(
                rowA,
                key
            );


        const valueB =
            getSortValue(
                rowB,
                key
            );


        let result = 0;


        /* =================================================
           DATE
           ================================================= */

        if (
            key === "last_active"
            ||
            key === "last_login"
        ) {

            result =
                getDateValue(
                    valueA
                )
                -
                getDateValue(
                    valueB
                );

        }


        /* =================================================
           TEXT
           ================================================= */

        else {

            result =
                String(
                    valueA
                )
                    .localeCompare(
                        String(
                            valueB
                        ),
                        undefined,
                        {
                            numeric:
                                true,

                            sensitivity:
                                "base"
                        }
                    );

        }


        return (
            direction === "desc"
                ? -result
                : result
        );

    }


    /* =====================================================
       FILTER
       ===================================================== */

    function getFilteredRows() {

        const query =
            normalize(
                search?.value
                ||
                ""
            );


        const role =
            roleFilter?.value
            ||
            "all";


        const status =
            statusFilter?.value
            ||
            "all";


        const security =
            securityFilter?.value
            ||
            "all";


        return rows.filter(
            (
                row
            ) => {

                const matchesSearch =
                    (
                        !query
                        ||
                        normalize(
                            row.dataset.search
                            ||
                            ""
                        )
                            .includes(
                                query
                            )
                    );


                const matchesRole =
                    (
                        role === "all"
                        ||
                        row.dataset.role
                        ===
                        role
                    );


                const matchesStatus =
                    (
                        status === "all"
                        ||
                        row.dataset.status
                        ===
                        status
                    );


                const matchesSecurity =
                    (
                        security === "all"
                        ||
                        row.dataset.security
                        ===
                        security
                    );


                return (
                    matchesSearch
                    &&
                    matchesRole
                    &&
                    matchesStatus
                    &&
                    matchesSecurity
                );

            }
        );

    }


    /* =====================================================
       FILTERED + SORTED ROWS
       ===================================================== */

    function getProcessedRows() {

        const filteredRows =
            getFilteredRows();


        if (
            !activeSortKey
            ||
            !activeSortDirection
        ) {

            return [
                ...filteredRows
            ];

        }


        return [
            ...filteredRows
        ].sort(
            (
                rowA,
                rowB
            ) => {

                return compareRows(
                    rowA,
                    rowB,
                    activeSortKey,
                    activeSortDirection
                );

            }
        );

    }


    /* =====================================================
       SORT ICON ROTATION
       Every click rotates 180 degrees,
       matching Registration Requests.
       ===================================================== */

    function rotateSortIcon(
        button
    ) {

        const previousRotation =
            Number(
                button.dataset
                    .sortRotation
                ||
                0
            );


        const nextRotation =
            previousRotation
            +
            180;


        button.dataset.sortRotation =
            String(
                nextRotation
            );


        button.style.setProperty(
            "--system-sort-rotation",
            `${nextRotation}deg`
        );

    }


    /* =====================================================
       SORT BUTTON UI
       ===================================================== */

    function updateSortButtonUI() {

        sortButtons.forEach(
            (
                button
            ) => {

                const key =
                    button.dataset
                        .systemSortKey;


                const active =
                    (
                        key
                        ===
                        activeSortKey
                    );


                button.classList.toggle(
                    "is-active",
                    active
                );


                button.setAttribute(
                    "aria-pressed",
                    active
                        ? "true"
                        : "false"
                );


                if (!active) {

                    button.title =
                        `Sort by ${key}`;

                    return;

                }


                button.title =
                    activeSortDirection
                    ===
                    "asc"

                        ? (
                            "Ascending — "
                            +
                            "click for descending"
                        )

                        : (
                            "Descending — "
                            +
                            "click for ascending"
                        );

            }
        );

    }


    /* =====================================================
       REFRESH PROCESSED ROWS
       ===================================================== */

    function refreshProcessedRows() {

        processedRows =
            getProcessedRows();

    }


    /* =====================================================
       FILTER EVENT
       ===================================================== */

    function applyFilters() {

        currentPage = 1;

        refreshProcessedRows();

        render();

    }


    /* =====================================================
       RENDER
       ===================================================== */

    function render() {

        const total =
            processedRows.length;


        const totalPages =
            Math.max(
                1,
                Math.ceil(
                    total
                    /
                    perPage
                )
            );


        if (
            currentPage
            >
            totalPages
        ) {

            currentPage =
                totalPages;

        }


        const start =
            (
                currentPage
                -
                1
            )
            *
            perPage;


        const end =
            Math.min(
                start
                +
                perPage,
                total
            );


        /* =================================================
           HIDE EVERYTHING
           ================================================= */

        rows.forEach(
            (
                row
            ) => {

                row.hidden =
                    true;

            }
        );


        /* =================================================
           REBUILD DOM ORDER
           Same sorting flow as Registration Requests
           ================================================= */

        if (tableBody) {

            const fragment =
                document
                    .createDocumentFragment();


            processedRows.forEach(
                (
                    row
                ) => {

                    fragment.appendChild(
                        row
                    );

                }
            );


            tableBody.appendChild(
                fragment
            );

        }


        /* =================================================
           SHOW CURRENT PAGE
           ================================================= */

        processedRows
            .slice(
                start,
                end
            )
            .forEach(
                (
                    row
                ) => {

                    row.hidden =
                        false;

                }
            );


        /* =================================================
           RESULT TEXT
           ================================================= */

        if (resultText) {

            if (
                total === 0
            ) {

                resultText.textContent =
                    "Showing 0 users";

            }

            else {

                resultText.textContent =
                    (
                        `Showing ${start + 1} `
                        +
                        `to ${end} `
                        +
                        `of ${total} users`
                    );

            }

        }


        /* =================================================
           PREVIOUS
           ================================================= */

        if (prevButton) {

            prevButton.disabled =
                (
                    currentPage
                    <=
                    1
                );

        }


        /* =================================================
           NEXT
           ================================================= */

        if (nextButton) {

            nextButton.disabled =
                (
                    currentPage
                    >=
                    totalPages
                );

        }


        renderPageNumbers(
            totalPages
        );

    }


    /* =====================================================
       PAGE NUMBERS
       ===================================================== */

    function renderPageNumbers(
        totalPages
    ) {

        if (
            !pageNumbers
        ) {
            return;
        }


        pageNumbers.innerHTML =
            "";


        const pages =
            [];


        if (
            totalPages
            <=
            5
        ) {

            for (
                let index = 1;
                index <= totalPages;
                index += 1
            ) {

                pages.push(
                    index
                );

            }

        }

        else {

            pages.push(
                1
            );


            if (
                currentPage
                >
                3
            ) {

                pages.push(
                    "..."
                );

            }


            const from =
                Math.max(
                    2,
                    currentPage
                    -
                    1
                );


            const to =
                Math.min(
                    totalPages
                    -
                    1,
                    currentPage
                    +
                    1
                );


            for (
                let index = from;
                index <= to;
                index += 1
            ) {

                pages.push(
                    index
                );

            }


            if (
                currentPage
                <
                totalPages
                -
                2
            ) {

                pages.push(
                    "..."
                );

            }


            pages.push(
                totalPages
            );

        }


        pages.forEach(
            (
                number
            ) => {

                if (
                    number
                    ===
                    "..."
                ) {

                    const ellipsis =
                        document
                            .createElement(
                                "span"
                            );


                    ellipsis.className =
                        "system-page-ellipsis";


                    ellipsis.textContent =
                        "...";


                    pageNumbers.appendChild(
                        ellipsis
                    );


                    return;

                }


                const button =
                    document
                        .createElement(
                            "button"
                        );


                button.type =
                    "button";


                button.className =
                    "system-page-number";


                button.textContent =
                    String(
                        number
                    );


                if (
                    number
                    ===
                    currentPage
                ) {

                    button.classList.add(
                        "is-active"
                    );

                }


                button.addEventListener(
                    "click",
                    () => {

                        currentPage =
                            number;


                        render();

                    }
                );


                pageNumbers.appendChild(
                    button
                );

            }
        );

    }


    /* =====================================================
       SORT CLICK
       Same click sequence as Registration Requests:
       1. determine ASC / DESC
       2. return to page 1
       3. update table
       4. update visual state
       5. rotate clicked icon
       ===================================================== */

    sortButtons.forEach(
        (
            button
        ) => {

            button.addEventListener(
                "click",
                (
                    event
                ) => {

                    event.preventDefault();

                    event.stopPropagation();


                    const key =
                        button.dataset
                            .systemSortKey;


                    if (!key) {
                        return;
                    }


                    /* =====================================
                       SAME COLUMN:
                       ASC -> DESC
                       DESC -> ASC
                       ===================================== */

                    if (
                        activeSortKey
                        ===
                        key
                    ) {

                        activeSortDirection =
                            (
                                activeSortDirection
                                ===
                                "asc"
                            )
                                ? "desc"
                                : "asc";

                    }


                    /* =====================================
                       NEW COLUMN:
                       START ASC
                       ===================================== */

                    else {

                        activeSortKey =
                            key;


                        activeSortDirection =
                            "asc";

                    }


                    /* =====================================
                       RETURN TO PAGE 1
                       ===================================== */

                    currentPage = 1;


                    /* =====================================
                       UPDATE TABLE
                       ===================================== */

                    refreshProcessedRows();

                    render();


                    /* =====================================
                       VISUAL FEEDBACK
                       ===================================== */

                    updateSortButtonUI();


                    rotateSortIcon(
                        button
                    );

                }
            );

        }
    );


    /* =====================================================
       SEARCH / FILTER EVENTS
       ===================================================== */

    search?.addEventListener(
        "input",
        applyFilters
    );


    roleFilter?.addEventListener(
        "change",
        applyFilters
    );


    statusFilter?.addEventListener(
        "change",
        applyFilters
    );


    securityFilter?.addEventListener(
        "change",
        applyFilters
    );


    /* =====================================================
       PAGINATION EVENTS
       ===================================================== */

    prevButton?.addEventListener(
        "click",
        () => {

            if (
                currentPage
                <=
                1
            ) {
                return;
            }


            currentPage -=
                1;


            render();

        }
    );


    nextButton?.addEventListener(
        "click",
        () => {

            const totalPages =
                Math.max(
                    1,
                    Math.ceil(
                        processedRows.length
                        /
                        perPage
                    )
                );


            if (
                currentPage
                >=
                totalPages
            ) {
                return;
            }


            currentPage +=
                1;


            render();

        }
    );


    /* =====================================================
       EXPORT CSV
       Export respects current search/filter/sort order.
       ===================================================== */

    exportButton?.addEventListener(
        "click",
        () => {

            const lines =
                [
                    [
                        "Name",
                        "Email",
                        "Role",
                        "Status",
                        "Security"
                    ]
                ];


            processedRows.forEach(
                (
                    row
                ) => {

                    const userCopy =
                        row.querySelector(
                            ".system-user-copy"
                        );


                    const name =
                        userCopy
                            ?.querySelector(
                                "strong"
                            )
                            ?.textContent
                            ?.trim()
                        ||
                        "";


                    const email =
                        userCopy
                            ?.querySelector(
                                "small"
                            )
                            ?.textContent
                            ?.trim()
                        ||
                        "";


                    lines.push(
                        [
                            name,

                            email,

                            row.dataset.role
                            ||
                            "",

                            row.dataset.status
                            ||
                            "",

                            row.dataset.security
                            ||
                            ""
                        ]
                    );

                }
            );


            const csv =
                lines
                    .map(
                        (
                            line
                        ) => {

                            return line
                                .map(
                                    (
                                        value
                                    ) => {

                                        const text =
                                            String(
                                                value
                                                ??
                                                ""
                                            );


                                        return (
                                            `"${text.replace(
                                                /"/g,
                                                '""'
                                            )}"`
                                        );

                                    }
                                )
                                .join(
                                    ","
                                );

                        }
                    )
                    .join(
                        "\n"
                    );


            const blob =
                new Blob(
                    [
                        csv
                    ],
                    {
                        type:
                            "text/csv;charset=utf-8"
                    }
                );


            const link =
                document.createElement(
                    "a"
                );


            link.href =
                URL.createObjectURL(
                    blob
                );


            link.download =
                "bika-system-users.csv";


            link.click();


            URL.revokeObjectURL(
                link.href
            );

        }
    );


    /* =====================================================
       INITIAL
       ===================================================== */

    refreshProcessedRows();

    updateSortButtonUI();

    render();


})();
