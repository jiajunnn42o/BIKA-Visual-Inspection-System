/* =========================================================
   BIKA REGISTRATION REQUESTS
   app/static/js/registration_requests.js
   ========================================================= */

(() => {

    "use strict";


    /* =====================================================
       PAGE
       ===================================================== */

    const page =
        document.querySelector(
            "[data-registration-page]"
        );


    if (!page) {
        return;
    }



    /* =====================================================
       TABLE ELEMENTS
       ===================================================== */

    const tableBody =
        page.querySelector(
            "[data-registration-table]"
        );


    const rows =
        Array.from(
            page.querySelectorAll(
                "[data-registration-row]"
            )
        );


    const searchInput =
        page.querySelector(
            "[data-registration-search]"
        );


    const resultCount =
        page.querySelector(
            "[data-result-count]"
        );


    const currentPageElement =
        page.querySelector(
            "[data-page-current]"
        );


    const previousButton =
        page.querySelector(
            "[data-page-previous]"
        );


    const nextButton =
        page.querySelector(
            "[data-page-next]"
        );


    const noResults =
        page.querySelector(
            "[data-no-results]"
        );



    /* =====================================================
       PAGINATION
       ===================================================== */

    const PAGE_SIZE = 8;

    let currentPage = 1;



    /* =====================================================
       SORT
       ===================================================== */

    const sortButtons =
        Array.from(
            page.querySelectorAll(
                "[data-sort-key]"
            )
        );


    let activeSortKey = null;

    let activeSortDirection = null;



    /* =====================================================
       MAIN FILTER
       ===================================================== */

    const filter =
        page.querySelector(
            "[data-assignment-filter]"
        );


    const filterTrigger =
        filter
            ? filter.querySelector(
                "[data-filter-trigger]"
            )
            : null;


    const filterMenu =
        filter
            ? filter.querySelector(
                "[data-filter-menu]"
            )
            : null;


    const filterLabel =
        filter
            ? filter.querySelector(
                "[data-filter-label]"
            )
            : null;


    const filterOptions =
        filter
            ? Array.from(
                filter.querySelectorAll(
                    "[data-filter-value]"
                )
            )
            : [];


    let activeFilter = "all";



    /* =====================================================
       REVIEW MODAL
       ===================================================== */

    const modalBackdrop =
        document.querySelector(
            "[data-modal-backdrop]"
        );


    const modalHost =
        document.querySelector(
            "[data-modal-host]"
        );


    const reviewButtons =
        Array.from(
            page.querySelectorAll(
                "[data-review-button]"
            )
        );


    let activeReviewUserId = null;

    let activeUniqueCheckUrl = null;


    /*
     * Snapshot for fields controlled by Save Changes.
     */

    let initialEditSnapshot = null;


    /*
     * Snapshot for entire modal.
     *
     * Includes rejection reason so closing the modal
     * can warn about unsaved rejection text too.
     */

    let initialModalSnapshot = null;



    /* =====================================================
       UNIQUE CHECK STATE
       ===================================================== */

    const uniqueStates =
        new Map();


    const uniqueTimers =
        new Map();


    const uniqueControllers =
        new Map();



    /* =====================================================
       BASIC HELPERS
       ===================================================== */

    function normalize(value) {

        return String(
            value ?? ""
        )
            .trim()
            .toLowerCase();

    }



    function normalizeUniqueFieldName(
        input
    ) {

        if (!input) {
            return "";
        }


        const raw =
            input.dataset.uniqueField
            ||
            input.name
            ||
            "";


        if (
            raw === "employee-id"
            ||
            raw === "employeeId"
        ) {

            return "employee_id";

        }


        return raw;

    }



    /* =====================================================
       TABLE SORT VALUE
       ===================================================== */

    function getSortValue(
        row,
        key
    ) {

        const map = {

            name:
                "sortName",

            username:
                "sortUsername",

            email:
                "sortEmail",

            phone:
                "sortPhone",

            employee:
                "sortEmployee",

            submitted:
                "sortSubmitted"

        };


        const datasetKey =
            map[key];


        if (!datasetKey) {
            return "";
        }


        return (
            row.dataset[datasetKey]
            ??
            ""
        );

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
            key === "submitted"
        ) {

            const timeA =
                valueA
                    ? new Date(valueA).getTime()
                    : 0;


            const timeB =
                valueB
                    ? new Date(valueB).getTime()
                    : 0;


            result =
                timeA - timeB;

        }



        /* =================================================
           PHONE
           ================================================= */

        else if (
            key === "phone"
        ) {

            const phoneA =
                String(valueA)
                    .replace(
                        /\D/g,
                        ""
                    );


            const phoneB =
                String(valueB)
                    .replace(
                        /\D/g,
                        ""
                    );


            result =
                phoneA.localeCompare(
                    phoneB,
                    undefined,
                    {
                        numeric: true
                    }
                );

        }



        /* =================================================
           TEXT / EMPLOYEE ID
           ================================================= */

        else {

            result =
                String(valueA)
                    .localeCompare(
                        String(valueB),
                        undefined,
                        {
                            numeric: true,
                            sensitivity: "base"
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
       FILTER + SEARCH
       ===================================================== */

    function getFilteredRows() {

        const query =
            normalize(
                searchInput
                    ? searchInput.value
                    : ""
            );


        return rows.filter(
            (row) => {

                const searchText =
                    normalize(
                        row.dataset.searchText
                    );


                const assignmentStatus =
                    row.dataset.assignmentStatus
                    ||
                    "unassigned";


                const matchesSearch =
                    (
                        !query
                        ||
                        searchText.includes(
                            query
                        )
                    );


                const matchesFilter =
                    (
                        activeFilter === "all"
                        ||
                        assignmentStatus === activeFilter
                    );


                return (
                    matchesSearch
                    &&
                    matchesFilter
                );

            }
        );

    }



    /* =====================================================
       SORTED / FILTERED ROWS
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
       SORT ICON
       ===================================================== */

    function rotateSortIcon(
        button
    ) {

        const previousRotation =
            Number(
                button.dataset.sortRotation
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
            "--rr-sort-rotation",
            `${nextRotation}deg`
        );

    }



    /* =====================================================
       SORT BUTTON UI
       ===================================================== */

    function updateSortButtonUI() {

        sortButtons.forEach(
            (button) => {

                const key =
                    button.dataset.sortKey;


                const active =
                    key === activeSortKey;


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
                    activeSortDirection === "asc"
                        ? "Ascending — click for descending"
                        : "Descending — click for ascending";

            }
        );

    }



    /* =====================================================
       SORT CLICK
       ===================================================== */

    sortButtons.forEach(
        (button) => {

            button.addEventListener(
                "click",
                (event) => {

                    event.preventDefault();

                    event.stopPropagation();


                    const key =
                        button.dataset.sortKey;


                    if (!key) {
                        return;
                    }


                    if (
                        activeSortKey === key
                    ) {

                        activeSortDirection =
                            activeSortDirection === "asc"
                                ? "desc"
                                : "asc";

                    }

                    else {

                        activeSortKey =
                            key;


                        activeSortDirection =
                            "asc";

                    }


                    currentPage = 1;


                    updateTable();

                    updateSortButtonUI();

                    rotateSortIcon(
                        button
                    );

                }
            );

        }
    );



    /* =====================================================
       RENDER TABLE
       ===================================================== */

    function updateTable() {

        if (!tableBody) {
            return;
        }


        const processedRows =
            getProcessedRows();


        const total =
            processedRows.length;


        const totalPages =
            Math.max(
                1,
                Math.ceil(
                    total / PAGE_SIZE
                )
            );


        if (
            currentPage > totalPages
        ) {

            currentPage =
                totalPages;

        }


        const startIndex =
            (
                currentPage - 1
            )
            *
            PAGE_SIZE;


        const endIndex =
            Math.min(
                startIndex
                +
                PAGE_SIZE,
                total
            );



        /* =================================================
           HIDE EVERYTHING
           ================================================= */

        rows.forEach(
            (row) => {

                row.hidden = true;

            }
        );



        /* =================================================
           REBUILD DOM ORDER
           ================================================= */

        const fragment =
            document.createDocumentFragment();


        processedRows.forEach(
            (row) => {

                fragment.appendChild(
                    row
                );

            }
        );


        tableBody.appendChild(
            fragment
        );



        /* =================================================
           CURRENT PAGE
           ================================================= */

        processedRows
            .slice(
                startIndex,
                endIndex
            )
            .forEach(
                (
                    row,
                    index
                ) => {

                    row.hidden =
                        false;


                    const numberCell =
                        row.querySelector(
                            "[data-row-number]"
                        );


                    if (numberCell) {

                        numberCell.textContent =
                            String(
                                startIndex
                                +
                                index
                                +
                                1
                            );

                    }

                }
            );



        /* =================================================
           NO RESULTS
           ================================================= */

        if (noResults) {

            noResults.hidden =
                total !== 0;

        }



        /* =================================================
           COUNT
           ================================================= */

        if (resultCount) {

            if (
                total === 0
            ) {

                resultCount.textContent =
                    "Showing 0 of 0 registrations";

            }

            else {

                resultCount.textContent =
                    `Showing ${startIndex + 1} to ${endIndex} of ${total} registrations`;

            }

        }



        /* =================================================
           CURRENT PAGE
           ================================================= */

        if (currentPageElement) {

            currentPageElement.textContent =
                String(
                    currentPage
                );

        }



        /* =================================================
           PREVIOUS
           ================================================= */

        if (previousButton) {

            previousButton.disabled =
                (
                    total === 0
                    ||
                    currentPage <= 1
                );

        }



        /* =================================================
           NEXT
           ================================================= */

        if (nextButton) {

            nextButton.disabled =
                (
                    total === 0
                    ||
                    currentPage >= totalPages
                );

        }

    }



    /* =====================================================
       SEARCH
       ===================================================== */

    if (searchInput) {

        searchInput.addEventListener(
            "input",
            () => {

                currentPage = 1;

                updateTable();

            }
        );

    }



    /* =====================================================
       PAGINATION
       ===================================================== */

    if (previousButton) {

        previousButton.addEventListener(
            "click",
            () => {

                if (
                    currentPage <= 1
                ) {
                    return;
                }


                currentPage -= 1;


                updateTable();

            }
        );

    }



    if (nextButton) {

        nextButton.addEventListener(
            "click",
            () => {

                const total =
                    getProcessedRows()
                        .length;


                const totalPages =
                    Math.max(
                        1,
                        Math.ceil(
                            total / PAGE_SIZE
                        )
                    );


                if (
                    currentPage >= totalPages
                ) {
                    return;
                }


                currentPage += 1;


                updateTable();

            }
        );

    }



    /* =====================================================
       MAIN FILTER
       ===================================================== */

    function openFilter() {

        if (
            !filter
            ||
            !filterTrigger
            ||
            !filterMenu
        ) {
            return;
        }


        filterMenu.hidden =
            false;


        filterTrigger.setAttribute(
            "aria-expanded",
            "true"
        );


        window.requestAnimationFrame(
            () => {

                filter.classList.add(
                    "is-open"
                );

            }
        );

    }



    function closeFilter() {

        if (
            !filter
            ||
            !filterTrigger
            ||
            !filterMenu
        ) {
            return;
        }


        filter.classList.remove(
            "is-open"
        );


        filterTrigger.setAttribute(
            "aria-expanded",
            "false"
        );


        window.setTimeout(
            () => {

                if (
                    !filter.classList.contains(
                        "is-open"
                    )
                ) {

                    filterMenu.hidden =
                        true;

                }

            },
            150
        );

    }



    if (filterTrigger) {

        filterTrigger.addEventListener(
            "click",
            (event) => {

                event.preventDefault();

                event.stopPropagation();


                if (
                    filter.classList.contains(
                        "is-open"
                    )
                ) {

                    closeFilter();

                }

                else {

                    openFilter();

                }

            }
        );

    }



    filterOptions.forEach(
        (option) => {

            option.addEventListener(
                "click",
                () => {

                    activeFilter =
                        option.dataset.filterValue
                        ||
                        "all";


                    currentPage = 1;


                    filterOptions.forEach(
                        (item) => {

                            const selected =
                                item === option;


                            item.classList.toggle(
                                "is-selected",
                                selected
                            );


                            item.setAttribute(
                                "aria-selected",
                                selected
                                    ? "true"
                                    : "false"
                            );

                        }
                    );


                    if (filterLabel) {

                        filterLabel.textContent =
                            option.dataset.filterLabel
                            ||
                            "Assignment: All";

                    }


                    closeFilter();

                    updateTable();

                }
            );

        }
    );



    /* =====================================================
       BEAUTIFUL SELECT
       ===================================================== */

    function openBeautifulSelect(
        wrapper
    ) {

        if (!wrapper) {
            return;
        }


        const trigger =
            wrapper.querySelector(
                "[data-beautiful-select-trigger]"
            );


        const menu =
            wrapper.querySelector(
                "[data-beautiful-select-menu]"
            );


        if (
            !trigger
            ||
            !menu
        ) {
            return;
        }


        menu.hidden =
            false;


        trigger.setAttribute(
            "aria-expanded",
            "true"
        );


        wrapper.classList.add(
            "is-open"
        );

    }



    function closeBeautifulSelect(
        wrapper
    ) {

        if (!wrapper) {
            return;
        }


        const trigger =
            wrapper.querySelector(
                "[data-beautiful-select-trigger]"
            );


        const menu =
            wrapper.querySelector(
                "[data-beautiful-select-menu]"
            );


        wrapper.classList.remove(
            "is-open"
        );


        if (trigger) {

            trigger.setAttribute(
                "aria-expanded",
                "false"
            );

        }


        if (menu) {

            menu.hidden =
                true;

        }

    }



    function closeAllBeautifulSelects(
        exceptWrapper = null
    ) {

        if (!modalHost) {
            return;
        }


        modalHost
            .querySelectorAll(
                "[data-beautiful-select]"
            )
            .forEach(
                (wrapper) => {

                    if (
                        wrapper === exceptWrapper
                    ) {
                        return;
                    }


                    closeBeautifulSelect(
                        wrapper
                    );

                }
            );

    }



    function initializeBeautifulSelects() {

        if (!modalHost) {
            return;
        }


        const wrappers =
            Array.from(
                modalHost.querySelectorAll(
                    "[data-beautiful-select]"
                )
            );


        wrappers.forEach(
            (wrapper) => {

                const nativeSelect =
                    wrapper.querySelector(
                        ".rr-native-select"
                    );


                const trigger =
                    wrapper.querySelector(
                        "[data-beautiful-select-trigger]"
                    );


                const label =
                    wrapper.querySelector(
                        "[data-beautiful-select-label]"
                    );


                const menu =
                    wrapper.querySelector(
                        "[data-beautiful-select-menu]"
                    );


                if (
                    !nativeSelect
                    ||
                    !trigger
                    ||
                    !label
                    ||
                    !menu
                ) {
                    return;
                }



                /* =========================================
                   LABEL
                   ========================================= */

                function syncLabel() {

                    const selected =
                        nativeSelect
                            .selectedOptions[0];


                    if (!selected) {
                        return;
                    }


                    label.textContent =
                        selected
                            .textContent
                            .trim();

                }



                /* =========================================
                   BUILD MENU
                   ========================================= */

                menu.innerHTML =
                    "";


                Array.from(
                    nativeSelect.options
                )
                .forEach(
                    (option) => {

                        const optionButton =
                            document.createElement(
                                "button"
                            );


                        optionButton.type =
                            "button";


                        optionButton.className =
                            "rr-beautiful-option";


                        optionButton.dataset.value =
                            option.value;


                        if (
                            option.selected
                        ) {

                            optionButton.classList.add(
                                "is-selected"
                            );

                        }



                        const text =
                            document.createElement(
                                "span"
                            );


                        text.textContent =
                            option
                                .textContent
                                .trim();



                        const check =
                            document.createElement(
                                "span"
                            );


                        check.className =
                            "rr-beautiful-option-check";


                        check.textContent =
                            "✓";


                        optionButton.append(
                            text,
                            check
                        );



                        optionButton.addEventListener(
                            "click",
                            (event) => {

                                event.preventDefault();

                                event.stopPropagation();


                                nativeSelect.value =
                                    option.value;


                                nativeSelect.dispatchEvent(
                                    new Event(
                                        "change",
                                        {
                                            bubbles: true
                                        }
                                    )
                                );


                                syncLabel();


                                menu
                                    .querySelectorAll(
                                        ".rr-beautiful-option"
                                    )
                                    .forEach(
                                        (item) => {

                                            item.classList.remove(
                                                "is-selected"
                                            );

                                        }
                                    );


                                optionButton.classList.add(
                                    "is-selected"
                                );


                                closeBeautifulSelect(
                                    wrapper
                                );

                            }
                        );


                        menu.appendChild(
                            optionButton
                        );

                    }
                );


                syncLabel();



                /* =========================================
                   TRIGGER
                   ========================================= */

                trigger.addEventListener(
                    "click",
                    (event) => {

                        event.preventDefault();

                        event.stopPropagation();


                        const alreadyOpen =
                            wrapper.classList.contains(
                                "is-open"
                            );


                        closeAllBeautifulSelects(
                            wrapper
                        );


                        if (alreadyOpen) {

                            closeBeautifulSelect(
                                wrapper
                            );

                        }

                        else {

                            openBeautifulSelect(
                                wrapper
                            );

                        }

                    }
                );

            }
        );

    }



    /* =====================================================
       REVIEW SUMMARY
       ===================================================== */

    function updateReviewSummary() {

        if (!modalHost) {
            return;
        }


        const fields =
            Array.from(
                modalHost.querySelectorAll(
                    "[data-summary-field]"
                )
            );


        fields.forEach(
            (field) => {

                const fieldName =
                    field.dataset.summaryField;


                if (!fieldName) {
                    return;
                }


                const summaryItem =
                    modalHost.querySelector(
                        `[data-summary-item="${fieldName}"]`
                    );


                if (!summaryItem) {
                    return;
                }


                const output =
                    summaryItem.querySelector(
                        "strong"
                    );


                const state =
                    summaryItem.querySelector(
                        ".rr-requirement-state"
                    );


                const value =
                    String(
                        field.value
                        ||
                        ""
                    ).trim();


                let displayValue =
                    value;


                if (
                    field.tagName === "SELECT"
                    &&
                    field.selectedOptions.length
                ) {

                    displayValue =
                        field
                            .selectedOptions[0]
                            .textContent
                            .trim();

                }


                const incomplete =
                    (
                        !value
                        ||
                        /^select\b/i.test(
                            displayValue
                        )
                    );


                if (output) {

                    output.textContent =
                        incomplete
                            ? "Not Assigned"
                            : displayValue;

                }


                summaryItem.classList.toggle(
                    "is-complete",
                    !incomplete
                );


                if (state) {

                    state.textContent =
                        incomplete
                            ? ""
                            : "✓";

                }

            }
        );

    }



    /* =====================================================
       SNAPSHOT HELPERS
       ===================================================== */

    function serializeEditableFields(
        container
    ) {

        if (!container) {
            return "[]";
        }


        const fields =
            Array.from(
                container.querySelectorAll(
                    `
                    input:not([type="hidden"]):not([readonly]):not([disabled]),
                    select:not([disabled]),
                    textarea:not([readonly]):not([disabled])
                    `
                )
            );


        return JSON.stringify(
            fields.map(
                (
                    field,
                    index
                ) => {

                    const key =
                        field.name
                        ||
                        field.id
                        ||
                        `${field.tagName}-${index}`;


                    let value =
                        field.value;


                    if (
                        field.type === "checkbox"
                        ||
                        field.type === "radio"
                    ) {

                        value =
                            field.checked;

                    }


                    return {
                        key,
                        value
                    };

                }
            )
        );

    }



    function getReviewEditForm() {

        if (!modalHost) {
            return null;
        }


        return (
            modalHost.querySelector(
                "[data-review-form]"
            )
            ||
            modalHost.querySelector(
                "#rr-review-edit-form"
            )
        );

    }



    function hasUnsavedEditChanges() {

        if (
            initialEditSnapshot === null
        ) {
            return false;
        }


        return (
            serializeEditableFields(
                getReviewEditForm()
            )
            !==
            initialEditSnapshot
        );

    }



    function hasUnsavedModalChanges() {

        if (
            initialModalSnapshot === null
        ) {
            return false;
        }


        return (
            serializeEditableFields(
                modalHost
            )
            !==
            initialModalSnapshot
        );

    }



    /* =====================================================
       UNIQUE INPUTS
       ===================================================== */

    function getUniqueInputs() {

        if (!modalHost) {
            return [];
        }


        const result = [];


        const usernameInput =
            modalHost.querySelector(
                `
                [data-unique-field="username"],
                input[name="username"]
                `
            );


        const employeeInput =
            modalHost.querySelector(
                `
                [data-unique-field="employee_id"],
                input[name="employee_id"]
                `
            );


        if (usernameInput) {

            usernameInput.dataset.uniqueField =
                "username";


            result.push(
                usernameInput
            );

        }


        if (employeeInput) {

            employeeInput.dataset.uniqueField =
                "employee_id";


            result.push(
                employeeInput
            );

        }


        return result;

    }



    /* =====================================================
       CREATE / FIND UNIQUE STATUS LABEL
       ===================================================== */

    function getUniqueStatusElement(
        input
    ) {

        if (
            !input
            ||
            !modalHost
        ) {
            return null;
        }


        const fieldName =
            normalizeUniqueFieldName(
                input
            );


        let status =
            modalHost.querySelector(
                `[data-unique-status="${fieldName}"]`
            );


        if (status) {
            return status;
        }



        /*
         * If HTML does not already contain the status,
         * create it automatically beside the field title.
         */

        const fieldWrapper =
            input.closest(
                ".rr-field"
            );


        if (!fieldWrapper) {
            return null;
        }


        const title =
            fieldWrapper.querySelector(
                ":scope > span"
            );


        if (!title) {
            return null;
        }


        title.classList.add(
            "rr-field-title-row"
        );


        status =
            document.createElement(
                "span"
            );


        status.className =
            "rr-unique-status";


        status.dataset.uniqueStatus =
            fieldName;


        status.setAttribute(
            "aria-live",
            "polite"
        );


        title.appendChild(
            status
        );


        return status;

    }



    /* =====================================================
       UNIQUE STATUS
       ===================================================== */

    function setUniqueStatus(
        input,
        state,
        message = ""
    ) {

        if (!input) {
            return;
        }


        const fieldName =
            normalizeUniqueFieldName(
                input
            );


        if (!fieldName) {
            return;
        }


        uniqueStates.set(
            fieldName,
            state
        );


        const status =
            getUniqueStatusElement(
                input
            );


        input.classList.remove(
            "is-unique-checking",
            "is-unique-available",
            "is-unique-unavailable"
        );


        if (status) {

            status.classList.remove(
                "is-checking",
                "is-available",
                "is-unavailable"
            );

        }



        /* =================================================
           CHECKING
           ================================================= */

        if (
            state === "checking"
        ) {

            input.classList.add(
                "is-unique-checking"
            );


            if (status) {

                status.classList.add(
                    "is-checking"
                );


                status.textContent =
                    message
                    ||
                    "Checking...";

            }

        }



        /* =================================================
           AVAILABLE
           ================================================= */

        else if (
            state === "available"
        ) {

            input.classList.add(
                "is-unique-available"
            );


            if (status) {

                status.classList.add(
                    "is-available"
                );


                status.textContent =
                    message
                    ||
                    "Available";

            }

        }



        /* =================================================
           UNAVAILABLE
           ================================================= */

        else if (
            state === "unavailable"
        ) {

            input.classList.add(
                "is-unique-unavailable"
            );


            if (status) {

                status.classList.add(
                    "is-unavailable"
                );


                status.textContent =
                    message
                    ||
                    "Already in use";

            }

        }



        /* =================================================
           CLEAR
           ================================================= */

        else {

            if (status) {

                status.textContent =
                    message;

            }

        }


        updateSaveButtonState();

    }



    /* =====================================================
       UNIQUE CHECK URL
       ===================================================== */

    function getUniqueCheckUrl(
        input
    ) {

        if (
            input
            &&
            input.dataset.uniqueUrl
        ) {

            return input.dataset.uniqueUrl;

        }


        return activeUniqueCheckUrl;

    }



    /* =====================================================
       CHECK UNIQUE FIELD
       ===================================================== */

    async function checkUniqueField(
        input
    ) {

        if (!input) {
            return false;
        }


        const fieldName =
            normalizeUniqueFieldName(
                input
            );


        const value =
            String(
                input.value
                ||
                ""
            ).trim();


        const endpoint =
            getUniqueCheckUrl(
                input
            );


        if (
            !fieldName
            ||
            !endpoint
        ) {

            setUniqueStatus(
                input,
                "unavailable",
                "Unable to verify"
            );


            return false;

        }



        /* =================================================
           EMPTY
           ================================================= */

        if (!value) {

            setUniqueStatus(
                input,
                "unavailable",
                "Required"
            );


            return false;

        }



        /* =================================================
           CANCEL OLD REQUEST
           ================================================= */

        const oldController =
            uniqueControllers.get(
                fieldName
            );


        if (oldController) {

            oldController.abort();

        }


        const controller =
            new AbortController();


        uniqueControllers.set(
            fieldName,
            controller
        );


        setUniqueStatus(
            input,
            "checking",
            "Checking..."
        );



        try {

            const url =
                new URL(
                    endpoint,
                    window.location.origin
                );


            url.searchParams.set(
                "field",
                fieldName
            );


            url.searchParams.set(
                "value",
                value
            );


            const response =
                await fetch(
                    url.toString(),
                    {

                        method:
                            "GET",

                        credentials:
                            "same-origin",

                        headers: {

                            "Accept":
                                "application/json",

                            "X-Requested-With":
                                "XMLHttpRequest"

                        },

                        signal:
                            controller.signal

                    }
                );


            if (!response.ok) {

                throw new Error(
                    `Unique check HTTP ${response.status}`
                );

            }


            const data =
                await response.json();



            /*
             * Ignore stale response if the user
             * changed the field while request was running.
             */

            if (
                String(
                    input.value
                    ||
                    ""
                ).trim()
                !==
                value
            ) {

                return false;

            }



            if (
                data.available === true
            ) {

                setUniqueStatus(
                    input,
                    "available",
                    data.message
                    ||
                    "Available"
                );


                return true;

            }


            setUniqueStatus(
                input,
                "unavailable",
                data.message
                ||
                "Already in use"
            );


            return false;

        }

        catch (error) {

            if (
                error.name === "AbortError"
            ) {

                return false;

            }


            console.error(
                "[BIKA] Unique check failed:",
                error
            );


            setUniqueStatus(
                input,
                "unavailable",
                "Unable to verify"
            );


            return false;

        }

    }



    /* =====================================================
       DEBOUNCED UNIQUE CHECK
       ===================================================== */

    function queueUniqueCheck(
        input
    ) {

        if (!input) {
            return;
        }


        const fieldName =
            normalizeUniqueFieldName(
                input
            );


        const previousTimer =
            uniqueTimers.get(
                fieldName
            );


        if (previousTimer) {

            window.clearTimeout(
                previousTimer
            );

        }


        setUniqueStatus(
            input,
            "checking",
            "Checking..."
        );


        const timer =
            window.setTimeout(
                () => {

                    checkUniqueField(
                        input
                    );

                },
                350
            );


        uniqueTimers.set(
            fieldName,
            timer
        );

    }



    /* =====================================================
       UNIQUE STATUS VALID
       ===================================================== */

    function allUniqueFieldsAvailable() {

        const inputs =
            getUniqueInputs();


        if (
            inputs.length === 0
        ) {

            return true;

        }


        return inputs.every(
            (input) => {

                const fieldName =
                    normalizeUniqueFieldName(
                        input
                    );


                return (
                    uniqueStates.get(
                        fieldName
                    )
                    ===
                    "available"
                );

            }
        );

    }



    /* =====================================================
       SAVE BUTTON
       ===================================================== */

    function getSaveButton() {

        if (!modalHost) {
            return null;
        }


        return (
            modalHost.querySelector(
                "[data-save-button]"
            )
            ||
            modalHost.querySelector(
                'button[form="rr-review-edit-form"]'
            )
        );

    }



    function updateSaveButtonState() {

        const saveButton =
            getSaveButton();


        if (!saveButton) {
            return;
        }


        const available =
            allUniqueFieldsAvailable();


        saveButton.disabled =
            !available;


        if (available) {

            saveButton.title =
                "";

        }

        else {

            saveButton.title =
                "Username and Employee ID must be available before saving.";

        }

    }



    /* =====================================================
       VALIDATE ALL UNIQUE FIELDS BEFORE SAVE
       ===================================================== */

    async function validateAllUniqueFields() {

        const inputs =
            getUniqueInputs();


        if (
            inputs.length === 0
        ) {

            return true;

        }


        const checks =
            inputs.map(
                (input) => {

                    const fieldName =
                        normalizeUniqueFieldName(
                            input
                        );


                    const timer =
                        uniqueTimers.get(
                            fieldName
                        );


                    if (timer) {

                        window.clearTimeout(
                            timer
                        );

                    }


                    return checkUniqueField(
                        input
                    );

                }
            );


        const results =
            await Promise.all(
                checks
            );


        return results.every(
            Boolean
        );

    }



    /* =====================================================
       INITIALIZE UNIQUE FIELDS
       ===================================================== */

    function initializeUniqueChecks() {

        uniqueStates.clear();


        const inputs =
            getUniqueInputs();


        inputs.forEach(
            (input) => {

                getUniqueStatusElement(
                    input
                );


                /*
                 * Initial state.
                 */

                setUniqueStatus(
                    input,
                    "checking",
                    "Checking..."
                );



                input.addEventListener(
                    "input",
                    () => {

                        queueUniqueCheck(
                            input
                        );


                        updateApprovalButton();

                    }
                );



                input.addEventListener(
                    "blur",
                    () => {

                        const fieldName =
                            normalizeUniqueFieldName(
                                input
                            );


                        const timer =
                            uniqueTimers.get(
                                fieldName
                            );


                        if (timer) {

                            window.clearTimeout(
                                timer
                            );

                        }


                        checkUniqueField(
                            input
                        );

                    }
                );



                /*
                 * Check existing current value.
                 *
                 * Backend excludes this applicant's own ID,
                 * so existing username / employee ID should
                 * return Available.
                 */

                checkUniqueField(
                    input
                );

            }
        );

    }



    /* =====================================================
       APPROVAL REQUIREMENTS
       ===================================================== */

    function requirementsAreComplete() {

        if (!modalHost) {
            return false;
        }


        const fields =
            Array.from(
                modalHost.querySelectorAll(
                    "[data-summary-field]"
                )
            );


        if (
            fields.length === 0
        ) {

            return false;

        }


        return fields.every(
            (field) => {

                const value =
                    String(
                        field.value
                        ||
                        ""
                    ).trim();


                if (!value) {
                    return false;
                }


                if (
                    field.tagName === "SELECT"
                    &&
                    field.selectedOptions.length
                ) {

                    const label =
                        field
                            .selectedOptions[0]
                            .textContent
                            .trim();


                    if (
                        /^select\b/i.test(
                            label
                        )
                    ) {

                        return false;

                    }

                }


                return true;

            }
        );

    }



    /* =====================================================
       APPROVE BUTTON
       ===================================================== */

    function getApproveButton() {

        if (!modalHost) {
            return null;
        }


        return (
            modalHost.querySelector(
                "[data-approve-button]"
            )
            ||
            modalHost.querySelector(
                'button[form="rr-approve-form"]'
            )
        );

    }



    function updateApprovalButton() {

        const approveButton =
            getApproveButton();


        if (!approveButton) {
            return;
        }


        const complete =
            requirementsAreComplete();


        const dirty =
            hasUnsavedEditChanges();


        /*
         * APPROVE is enabled only when:
         *
         * 1. Job Title exists
         * 2. Department exists
         * 3. Shift exists
         * 4. Access Role exists
         * 5. All form changes have been saved
         */

        approveButton.disabled =
            (
                !complete
                ||
                dirty
            );


        if (!complete) {

            approveButton.title =
                "Complete all approval requirements first.";

        }

        else if (dirty) {

            approveButton.title =
                "Save changes before approving.";

        }

        else {

            approveButton.title =
                "";

        }

    }



    /* =====================================================
       REJECTION STATE
       ===================================================== */

    function updateRejectionState() {

        if (!modalHost) {
            return;
        }


        const reason =
            modalHost.querySelector(
                "[data-reject-reason]"
            )
            ||
            modalHost.querySelector(
                'textarea[name="reason"]'
            );


        const counter =
            modalHost.querySelector(
                "[data-reason-count]"
            );


        const button =
            modalHost.querySelector(
                "[data-reject-button]"
            );


        if (!reason) {
            return;
        }


        const value =
            reason.value
            ||
            "";


        if (counter) {

            counter.textContent =
                `${value.length} / 500`;

        }


        if (button) {

            button.disabled =
                value.trim().length === 0;

        }

    }



    /* =====================================================
       SAVE SUCCESS TOAST
       ===================================================== */

    function showSaveSuccessToast() {

        const existing =
            document.querySelector(
                "[data-save-success-toast]"
            );


        if (existing) {

            existing.remove();

        }


        const toast =
            document.createElement(
                "div"
            );


        toast.className =
            "rr-save-success-toast";


        toast.setAttribute(
            "data-save-success-toast",
            ""
        );


        toast.innerHTML = `

            <iconsax-icon
                name="tick-circle"
                type="bold"
                size="21"
                color="currentColor"
                aria-hidden="true"
            ></iconsax-icon>

            <div>

                <strong>
                    Saved successfully
                </strong>

                <span>
                    Registration changes have been saved.
                </span>

            </div>

        `;


        document.body.appendChild(
            toast
        );


        window.requestAnimationFrame(
            () => {

                toast.classList.add(
                    "is-visible"
                );

            }
        );


        window.setTimeout(
            () => {

                toast.classList.remove(
                    "is-visible"
                );


                window.setTimeout(
                    () => {

                        toast.remove();

                    },
                    220
                );

            },
            2600
        );

    }



    /* =====================================================
       DISCARD DIALOG
       ===================================================== */

    function getDiscardDialog() {

        let dialog =
            document.querySelector(
                "[data-review-discard-dialog]"
            );


        if (dialog) {
            return dialog;
        }


        dialog =
            document.createElement(
                "div"
            );


        dialog.className =
            "rr-discard-backdrop";


        dialog.setAttribute(
            "data-review-discard-dialog",
            ""
        );


        dialog.hidden =
            true;


        dialog.innerHTML = `

            <div
                class="rr-discard-dialog"
                role="dialog"
                aria-modal="true"
                aria-labelledby="rr-discard-title"
            >

                <div class="rr-discard-icon">
                    !
                </div>

                <h3 id="rr-discard-title">
                    Discard changes?
                </h3>

                <p>
                    You have unsaved changes.
                    Closing this review will discard them.
                </p>

                <div class="rr-discard-actions">

                    <button
                        type="button"
                        class="rr-discard-cancel"
                        data-discard-cancel
                    >
                        Continue Editing
                    </button>

                    <button
                        type="button"
                        class="rr-discard-confirm"
                        data-discard-confirm
                    >
                        Discard Changes
                    </button>

                </div>

            </div>

        `;


        document.body.appendChild(
            dialog
        );


        const cancel =
            dialog.querySelector(
                "[data-discard-cancel]"
            );


        const confirm =
            dialog.querySelector(
                "[data-discard-confirm]"
            );


        if (cancel) {

            cancel.addEventListener(
                "click",
                () => {

                    hideDiscardDialog();

                }
            );

        }


        if (confirm) {

            confirm.addEventListener(
                "click",
                () => {

                    hideDiscardDialog();

                    performCloseReviewModal();

                }
            );

        }



        /*
         * Background click deliberately does nothing.
         */

        dialog.addEventListener(
            "click",
            (event) => {

                if (
                    event.target === dialog
                ) {

                    event.preventDefault();

                    event.stopPropagation();

                }

            }
        );


        return dialog;

    }



    function showDiscardDialog() {

        const dialog =
            getDiscardDialog();


        dialog.hidden =
            false;


        window.requestAnimationFrame(
            () => {

                dialog.classList.add(
                    "is-open"
                );

            }
        );

    }



    function hideDiscardDialog() {

        const dialog =
            document.querySelector(
                "[data-review-discard-dialog]"
            );


        if (!dialog) {
            return;
        }


        dialog.classList.remove(
            "is-open"
        );


        window.setTimeout(
            () => {

                dialog.hidden =
                    true;

            },
            150
        );

    }



    /* =====================================================
       APPROVE / REJECT CONFIRMATION
       ===================================================== */

    function getActionConfirmationDialog() {

        let backdrop =
            document.querySelector(
                "[data-action-confirm]"
            );


        if (backdrop) {
            return backdrop;
        }


        backdrop =
            document.createElement(
                "div"
            );


        backdrop.className =
            "rr-action-confirm-backdrop";


        backdrop.setAttribute(
            "data-action-confirm",
            ""
        );


        backdrop.hidden =
            true;


        document.body.appendChild(
            backdrop
        );


        backdrop.addEventListener(
            "click",
            (event) => {

                if (
                    event.target === backdrop
                ) {

                    event.preventDefault();

                    event.stopPropagation();

                }

            }
        );


        return backdrop;

    }



    function hideActionConfirmation() {

        const backdrop =
            document.querySelector(
                "[data-action-confirm]"
            );


        if (!backdrop) {
            return;
        }


        backdrop.classList.remove(
            "is-open"
        );


        window.setTimeout(
            () => {

                backdrop.hidden =
                    true;


                backdrop.innerHTML =
                    "";

            },
            160
        );

    }



    function showActionConfirmation(
        type,
        form
    ) {

        if (!form) {
            return;
        }


        const backdrop =
            getActionConfirmationDialog();


        const isApprove =
            type === "approve";


        const title =
            isApprove
                ? "Approve registration?"
                : "Reject registration?";


        const message =
            isApprove
                ? (
                    "This account will become active "
                    +
                    "and the applicant will be notified."
                )
                : (
                    "This registration request will be rejected "
                    +
                    "and the applicant will be notified."
                );


        const actionText =
            isApprove
                ? "Approve"
                : "Reject";


        const icon =
            isApprove
                ? "✓"
                : "!";


        backdrop.innerHTML = `

            <div
                class="rr-action-confirm-dialog"
                role="dialog"
                aria-modal="true"
            >

                <div class="rr-action-confirm-icon">
                    ${icon}
                </div>

                <h3>
                    ${title}
                </h3>

                <p>
                    ${message}
                </p>

                <div class="rr-action-confirm-actions">

                    <button
                        type="button"
                        class="rr-action-confirm-cancel"
                        data-action-cancel
                    >
                        Cancel
                    </button>

                    <button
                        type="button"
                        class="rr-action-confirm-submit"
                        data-action-submit
                    >
                        ${actionText}
                    </button>

                </div>

            </div>

        `;


        backdrop.hidden =
            false;


        window.requestAnimationFrame(
            () => {

                backdrop.classList.add(
                    "is-open"
                );

            }
        );


        const cancel =
            backdrop.querySelector(
                "[data-action-cancel]"
            );


        const submit =
            backdrop.querySelector(
                "[data-action-submit]"
            );


        if (cancel) {

            cancel.addEventListener(
                "click",
                () => {

                    hideActionConfirmation();

                }
            );

        }


        if (submit) {

            submit.addEventListener(
                "click",
                () => {

                    submit.disabled =
                        true;


                    /*
                     * Native form submit bypasses the
                     * confirmation submit listener.
                     */

                    HTMLFormElement
                        .prototype
                        .submit
                        .call(
                            form
                        );

                }
            );

        }

    }



    /* =====================================================
       CLOSE REVIEW
       ===================================================== */

    function cleanupReviewState() {

        uniqueTimers.forEach(
            (timer) => {

                window.clearTimeout(
                    timer
                );

            }
        );


        uniqueTimers.clear();


        uniqueControllers.forEach(
            (controller) => {

                controller.abort();

            }
        );


        uniqueControllers.clear();

        uniqueStates.clear();


        activeReviewUserId =
            null;


        activeUniqueCheckUrl =
            null;


        initialEditSnapshot =
            null;


        initialModalSnapshot =
            null;

    }



    function performCloseReviewModal() {

        if (
            !modalBackdrop
            ||
            !modalHost
            ||
            modalBackdrop.hidden
        ) {
            return;
        }


        /* =====================================================
        CLOSE OPEN DROPDOWNS / SMALL DIALOGS
        ===================================================== */

        closeAllBeautifulSelects();

        hideDiscardDialog();

        hideActionConfirmation();



        /* =====================================================
        CLOSE MODAL VISUALLY
        ===================================================== */

        modalBackdrop.classList.remove(
            "is-open"
        );



        /* =====================================================
        IMPORTANT:
        REMOVE REVIEW PARAMETER FROM URL

        Example:

        BEFORE:
        /superadmin/registrations?status=pending&review=15

        AFTER:
        /superadmin/registrations?status=pending
        ===================================================== */

        const currentUrl =
            new URL(
                window.location.href
            );


        currentUrl.searchParams.delete(
            "review"
        );


        currentUrl.searchParams.delete(
            "saved"
        );


        window.history.replaceState(
            {},
            "",
            currentUrl.toString()
        );



        /* =====================================================
        RESET REVIEW STATE
        ===================================================== */

        cleanupReviewState();



        /* =====================================================
        REMOVE MODAL CONTENT
        ===================================================== */

        window.setTimeout(
            () => {

                modalBackdrop.hidden =
                    true;


                modalHost.innerHTML =
                    "";


                document.documentElement
                    .style
                    .overflow =
                    "";

            },
            180
        );

    }



    function requestCloseReviewModal() {

        /*
         * Only X calls this function.
         *
         * If anything editable changed,
         * ask before closing.
         */

        if (
            hasUnsavedModalChanges()
        ) {

            showDiscardDialog();

            return;

        }


        performCloseReviewModal();

    }



    /* =====================================================
       INITIALIZE LOADED REVIEW
       ===================================================== */

    function initializeLoadedReview() {

        if (!modalHost) {
            return;
        }



        /* =================================================
           BEAUTIFUL SELECTS
           ================================================= */

        initializeBeautifulSelects();



        /* =================================================
           SUMMARY
           ================================================= */

        updateReviewSummary();



        /* =================================================
           SNAPSHOTS

           Take these BEFORE the user changes anything.
           ================================================= */

        initialEditSnapshot =
            serializeEditableFields(
                getReviewEditForm()
            );


        initialModalSnapshot =
            serializeEditableFields(
                modalHost
            );



        /* =================================================
           UNIQUE CHECKS
           ================================================= */

        initializeUniqueChecks();



        /* =================================================
           REVIEW FORM
           ================================================= */

        const reviewForm =
            getReviewEditForm();


        if (reviewForm) {


            reviewForm.addEventListener(
                "input",
                () => {

                    updateApprovalButton();

                }
            );


            reviewForm.addEventListener(
                "change",
                () => {

                    updateReviewSummary();

                    updateApprovalButton();

                }
            );



            /*
             * SAVE CHANGES
             *
             * Always verify Username + Employee ID
             * again immediately before submitting.
             */

            reviewForm.addEventListener(
                "submit",
                async (event) => {

                    event.preventDefault();


                    const saveButton =
                        getSaveButton();


                    if (saveButton) {

                        saveButton.disabled =
                            true;

                    }


                    const valid =
                        await validateAllUniqueFields();


                    if (!valid) {

                        updateSaveButtonState();

                        return;

                    }



                    /*
                     * Backend still performs the same
                     * unique validation again.
                     */

                    HTMLFormElement
                        .prototype
                        .submit
                        .call(
                            reviewForm
                        );

                }
            );

        }



        /* =================================================
           SUMMARY FIELDS
           ================================================= */

        const summaryFields =
            Array.from(
                modalHost.querySelectorAll(
                    "[data-summary-field]"
                )
            );


        summaryFields.forEach(
            (field) => {

                field.addEventListener(
                    "change",
                    () => {

                        updateReviewSummary();

                        updateApprovalButton();

                    }
                );

            }
        );



        /* =================================================
           REJECTION
           ================================================= */

        const rejectReason =
            modalHost.querySelector(
                "[data-reject-reason]"
            )
            ||
            modalHost.querySelector(
                'textarea[name="reason"]'
            );


        if (rejectReason) {

            rejectReason.addEventListener(
                "input",
                () => {

                    updateRejectionState();

                }
            );

        }


        updateRejectionState();



        /* =================================================
           APPROVE FORM
           ================================================= */

        const approveForm =
            modalHost.querySelector(
                "[data-approve-form]"
            )
            ||
            modalHost.querySelector(
                "#rr-approve-form"
            );


        if (approveForm) {

            approveForm.addEventListener(
                "submit",
                (event) => {

                    event.preventDefault();


                    updateApprovalButton();


                    const approveButton =
                        getApproveButton();


                    if (
                        approveButton
                        &&
                        approveButton.disabled
                    ) {

                        return;

                    }


                    showActionConfirmation(
                        "approve",
                        approveForm
                    );

                }
            );

        }



        /* =================================================
           REJECT FORM
           ================================================= */

        const rejectForm =
            modalHost.querySelector(
                "[data-reject-form]"
            )
            ||
            modalHost.querySelector(
                'form[action$="/reject"]'
            );


        if (rejectForm) {

            rejectForm.addEventListener(
                "submit",
                (event) => {

                    event.preventDefault();


                    updateRejectionState();


                    const rejectButton =
                        modalHost.querySelector(
                            "[data-reject-button]"
                        );


                    if (
                        rejectButton
                        &&
                        rejectButton.disabled
                    ) {

                        return;

                    }


                    showActionConfirmation(
                        "reject",
                        rejectForm
                    );

                }
            );

        }



        /* =================================================
           INITIAL APPROVAL STATE
           ================================================= */

        updateApprovalButton();

        updateSaveButtonState();

    }



    /* =====================================================
       OPEN REVIEW
       ===================================================== */

    async function openReviewModal(
        button
    ) {

        if (
            !modalBackdrop
            ||
            !modalHost
        ) {
            return;
        }


        const reviewUrl =
            button.dataset.reviewUrl;


        if (!reviewUrl) {
            return;
        }



        /* =================================================
           CURRENT USER
           ================================================= */

        activeReviewUserId =
            button.dataset.userId
            ||
            null;



        /*
         * Derive:
         *
         * /superadmin/registrations/15
         *
         * into:
         *
         * /superadmin/registrations/15/check-unique
         */

        try {

            const parsedUrl =
                new URL(
                    reviewUrl,
                    window.location.origin
                );


            let pathname =
                parsedUrl.pathname;


            pathname =
                pathname.replace(
                    /\/$/,
                    ""
                );


            activeUniqueCheckUrl =
                `${pathname}/check-unique`;

        }

        catch (error) {

            console.error(
                "[BIKA] Unable to derive unique URL:",
                error
            );


            activeUniqueCheckUrl =
                null;

        }



        button.disabled =
            true;


        try {

            const response =
                await fetch(
                    reviewUrl,
                    {

                        method:
                            "GET",

                        credentials:
                            "same-origin",

                        headers: {

                            "X-Requested-With":
                                "XMLHttpRequest",

                            "Accept":
                                "text/html"

                        }

                    }
                );


            if (!response.ok) {

                throw new Error(
                    `Unable to load review (${response.status})`
                );

            }


            modalHost.innerHTML =
                await response.text();


            modalBackdrop.hidden =
                false;


            document.documentElement
                .style
                .overflow =
                "hidden";


            window.requestAnimationFrame(
                () => {

                    modalBackdrop.classList.add(
                        "is-open"
                    );

                }
            );


            initializeLoadedReview();

        }

        catch (error) {

            console.error(
                "[BIKA] Unable to open review:",
                error
            );


            window.alert(
                "Unable to open this registration request. Please try again."
            );

        }

        finally {

            button.disabled =
                false;

        }

    }



    /* =====================================================
       REVIEW BUTTONS
       ===================================================== */

    reviewButtons.forEach(
        (button) => {

            button.addEventListener(
                "click",
                () => {

                    openReviewModal(
                        button
                    );

                }
            );

        }
    );



    /* =====================================================
       REVIEW MODAL CLICK

       IMPORTANT:
       Only X can close the main review modal.
       ===================================================== */

    if (modalBackdrop) {

        modalBackdrop.addEventListener(
            "click",
            (event) => {

                const closeButton =
                    event.target.closest(
                        "[data-modal-close]"
                    );


                if (closeButton) {

                    event.preventDefault();

                    event.stopPropagation();


                    requestCloseReviewModal();

                    return;

                }



                /*
                 * Clicking blurred backdrop does nothing.
                 */

                if (
                    event.target === modalBackdrop
                ) {

                    event.preventDefault();

                    event.stopPropagation();

                }

            }
        );

    }



    /* =====================================================
       DOCUMENT CLICK
       ===================================================== */

    document.addEventListener(
        "click",
        (event) => {


            /* =================================================
               MAIN FILTER
               ================================================= */

            if (
                filter
                &&
                filter.classList.contains(
                    "is-open"
                )
                &&
                !filter.contains(
                    event.target
                )
            ) {

                closeFilter();

            }



            /* =================================================
               MODAL BEAUTIFUL SELECT
               ================================================= */

            if (modalHost) {

                const beautifulSelect =
                    event.target.closest(
                        "[data-beautiful-select]"
                    );


                if (!beautifulSelect) {

                    closeAllBeautifulSelects();

                }

            }

        }
    );



    /* =====================================================
       ESCAPE

       ESC does NOT close Review.
       It only closes small dropdowns.
       ===================================================== */

    document.addEventListener(
        "keydown",
        (event) => {

            if (
                event.key !== "Escape"
            ) {
                return;
            }



            /* MAIN FILTER */

            if (
                filter
                &&
                filter.classList.contains(
                    "is-open"
                )
            ) {

                closeFilter();

                return;

            }



            /* CUSTOM SELECT */

            if (modalHost) {

                const openSelect =
                    modalHost.querySelector(
                        ".rr-beautiful-select.is-open"
                    );


                if (openSelect) {

                    closeBeautifulSelect(
                        openSelect
                    );

                }

            }


            /*
             * Do NOT close:
             *
             * - Review modal
             * - Discard confirmation
             * - Approve confirmation
             * - Reject confirmation
             */

        }
    );



    /* =====================================================
       AUTO REOPEN AFTER SAVE
       ===================================================== */

    const currentUrl =
        new URL(
            window.location.href
        );


    const reviewId =
        currentUrl.searchParams.get(
            "review"
        );


    const savedParam =
        currentUrl.searchParams.get(
            "saved"
        );


    if (reviewId) {

        const button =
            reviewButtons.find(
                (item) => {

                    return (
                        String(
                            item.dataset.userId
                        )
                        ===
                        String(
                            reviewId
                        )
                    );

                }
            );


        if (button) {

            openReviewModal(
                button
            );

        }

    }



    /* =====================================================
       SAVE SUCCESS DETECTION
       ===================================================== */

    let shouldShowSavedToast =
        savedParam === "1";


    /*
     * Fallback:
     *
     * Even if routes.py has not yet added ?saved=1,
     * detect the existing Flask success flash.
     */

    const successFlash =
        document.querySelector(
            ".rr-flash-success"
        );


    if (successFlash) {

        const flashText =
            String(
                successFlash.textContent
                ||
                ""
            ).toLowerCase();


        if (
            flashText.includes(
                "saved"
            )
            ||
            flashText.includes(
                "changes saved"
            )
        ) {

            shouldShowSavedToast =
                true;


            /*
             * Avoid showing both large flash
             * and small toast for the same save.
             */

            successFlash.remove();

        }

    }



    if (shouldShowSavedToast) {

        window.setTimeout(
            () => {

                showSaveSuccessToast();

            },
            reviewId
                ? 450
                : 150
        );



        /*
         * Remove saved=1 so refresh does not
         * show the toast again.
         */

        if (
            currentUrl.searchParams.has(
                "saved"
            )
        ) {

            currentUrl.searchParams.delete(
                "saved"
            );


            window.history.replaceState(
                {},
                "",
                currentUrl.toString()
            );

        }

    }



    /* =====================================================
       INITIAL TABLE
       ===================================================== */

    updateSortButtonUI();

    updateTable();

})();