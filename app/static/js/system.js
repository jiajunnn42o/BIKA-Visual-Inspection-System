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
       USER EDIT MODAL
       ===================================================== */

    const editButtons =
        Array.from(
            page.querySelectorAll(
                "[data-system-edit-user]"
            )
        );


    const userModal =
        page.querySelector(
            "[data-system-user-modal]"
        );


    const userModalCloseButtons =
        Array.from(
            page.querySelectorAll(
                "[data-system-user-modal-close]"
            )
        );


    const userModalLoading =
        page.querySelector(
            "[data-system-user-modal-loading]"
        );


    const userModalContent =
        page.querySelector(
            "[data-system-user-modal-content]"
        );


    const userModalError =
        page.querySelector(
            "[data-system-user-modal-error]"
        );


    const editAvatar =
        page.querySelector(
            "[data-system-edit-avatar]"
        );


    const editInitials =
        page.querySelector(
            "[data-system-edit-initials]"
        );


    const editName =
        page.querySelector(
            "[data-system-edit-name]"
        );


    const editEmail =
        page.querySelector(
            "[data-system-edit-email]"
        );


    const editUsername =
        page.querySelector(
            "[data-system-edit-username]"
        );


    const editReadonlyName =
        page.querySelector(
            "[data-system-edit-readonly-name]"
        );


    const editEmployeeId =
        page.querySelector(
            "[data-system-edit-employee-id]"
        );


    const editPhone =
        page.querySelector(
            "[data-system-edit-phone]"
        );


    const editDepartment =
        page.querySelector(
            "[data-system-edit-department]"
        );


    const editJobTitle =
        page.querySelector(
            "[data-system-edit-job-title]"
        );


    const editShift =
        page.querySelector(
            "[data-system-edit-shift]"
        );


    const editRole =
        page.querySelector(
            "[data-system-edit-role]"
        );


    const editRoleHelp =
        page.querySelector(
            "[data-system-edit-role-help]"
        );


    const editStatusBadge =
        page.querySelector(
            "[data-system-edit-status-badge]"
        );


    const editStatusAction =
        page.querySelector(
            "[data-system-edit-status-action]"
        );


    const editStatusHelp =
        page.querySelector(
            "[data-system-edit-status-help]"
        );


    const editProtection =
        page.querySelector(
            "[data-system-edit-protection]"
        );


    const editSaveButton =
        page.querySelector(
            "[data-system-user-save]"
        );


    const userConfirm =
        page.querySelector(
            "[data-system-user-confirm]"
        );


    const userConfirmMessage =
        page.querySelector(
            "[data-system-user-confirm-message]"
        );


    const userConfirmCancel =
        page.querySelector(
            "[data-system-user-confirm-cancel]"
        );


    const userConfirmSave =
        page.querySelector(
            "[data-system-user-confirm-save]"
        );


    const userConfirmTitle =
        page.querySelector(
            "[data-system-user-confirm-title]"
        );


    const userConfirmPasswordWrap =
        page.querySelector(
            "[data-system-user-confirm-password-wrap]"
        );


    const userConfirmPassword =
        page.querySelector(
            "[data-system-user-confirm-password]"
        );


    const userConfirmPasswordToggle =
        page.querySelector(
            "[data-system-user-confirm-password-toggle]"
        );


    const userConfirmPasswordEye =
        page.querySelector(
            "[data-system-user-confirm-password-eye]"
        );


    const userConfirmPasswordError =
        page.querySelector(
            "[data-system-user-confirm-password-error]"
        );


    let activeEditButton = null;

    let activeUserData = null;

    let originalRole = "";

    let pendingStatusAction = "none";

    let editBusy = false;


    /* =====================================================
       USER EDIT HELPERS
       ===================================================== */

    function getCsrfToken() {

        return (
            document.querySelector(
                'meta[name="csrf-token"]'
            )
            ?.content
            ||
            ""
        );

    }


    function setUserModalError(
        message = ""
    ) {

        if (
            userModalError
        ) {

            userModalError.textContent =
                message;

        }

    }


    function displayValue(
        value
    ) {

        const text =
            String(
                value
                ??
                ""
            )
                .trim();


        return (
            text
            ||
            "—"
        );

    }


    function setText(
        element,
        value
    ) {

        if (!element) {
            return;
        }


        element.textContent =
            displayValue(
                value
            );

    }


    function statusDestination(
        status,
        action
    ) {

        if (
            action === "disable"
        ) {
            return "disabled";
        }


        if (
            action === "reactivate"
            ||
            action === "unlock"
        ) {
            return "active";
        }


        return status;

    }


    function statusLabel(
        status
    ) {

        const labels = {

            active:
                "Active",

            disabled:
                "Disabled",

            locked:
                "Locked",

            pending:
                "Pending",

            rejected:
                "Rejected"

        };


        return (
            labels[status]
            ||
            String(
                status
                ||
                "Unknown"
            )
                .replace(
                    /_/g,
                    " "
                )
                .replace(
                    /\b\w/g,
                    (
                        character
                    ) => {

                        return character
                            .toUpperCase();

                    }
                )
        );

    }


    function actionForStatus(
        status
    ) {

        if (
            status === "active"
        ) {

            return {
                action:
                    "disable",

                label:
                    "Disable Account",

                help:
                    "Disables login access while keeping the account and history."
            };

        }


        if (
            status === "disabled"
        ) {

            return {
                action:
                    "reactivate",

                label:
                    "Reactivate Account",

                help:
                    "Restores login access for this account."
            };

        }


        if (
            status === "locked"
        ) {

            return {
                action:
                    "unlock",

                label:
                    "Unlock Account",

                help:
                    "Clears the security lock and restores login access."
            };

        }


        return {
            action:
                "none",

            label:
                "Managed elsewhere",

            help:
                "This status is controlled by the registration workflow."
        };

    }


    function renderEditAvatar(
        data
    ) {

        if (!editAvatar) {
            return;
        }


        editAvatar.innerHTML =
            "";


        if (
            data.profile_photo_url
        ) {

            const image =
                document.createElement(
                    "img"
                );


            image.src =
                data.profile_photo_url;


            image.alt =
                "";


            editAvatar.appendChild(
                image
            );


            return;

        }


        const initials =
            document.createElement(
                "span"
            );


        initials.textContent =
            data.initials
            ||
            "U";


        editAvatar.appendChild(
            initials
        );

    }


    function updateStatusControl() {

        if (
            !activeUserData
            ||
            !editStatusBadge
            ||
            !editStatusAction
        ) {
            return;
        }


        const destination =
            statusDestination(
                activeUserData.status,
                pendingStatusAction
            );


        editStatusBadge.textContent =
            statusLabel(
                destination
            );


        editStatusBadge.className =
            (
                "system-user-status-badge "
                +
                `is-${destination}`
            );


        editStatusAction.classList.remove(
            "is-positive",
            "is-undo"
        );


        if (
            !activeUserData.can_change_status
        ) {

            editStatusAction.disabled =
                true;


            editStatusAction.textContent =
                "Protected";


            if (
                editStatusHelp
            ) {

                editStatusHelp.textContent =
                    (
                        activeUserData.status_help
                        ||
                        "This account status cannot be changed here."
                    );

            }


            return;

        }


        if (
            pendingStatusAction
            !==
            "none"
        ) {

            editStatusAction.disabled =
                false;


            editStatusAction.textContent =
                "Undo Status Change";


            editStatusAction.classList.add(
                "is-undo"
            );


            if (
                editStatusHelp
            ) {

                editStatusHelp.textContent =
                    (
                        "This status change will be applied "
                        +
                        "after Save Changes."
                    );

            }


            return;

        }


        const config =
            actionForStatus(
                activeUserData.status
            );


        editStatusAction.textContent =
            config.label;


        editStatusAction.disabled =
            (
                config.action
                ===
                "none"
            );


        if (
            config.action === "reactivate"
            ||
            config.action === "unlock"
        ) {

            editStatusAction.classList.add(
                "is-positive"
            );

        }


        if (
            editStatusHelp
        ) {

            editStatusHelp.textContent =
                config.help;

        }

    }


    function hasEditChanges() {

        if (
            !activeUserData
        ) {
            return false;
        }


        const roleChanged =
            (
                editRole
                &&
                editRole.value
                !==
                originalRole
            );


        const statusChanged =
            (
                pendingStatusAction
                !==
                "none"
            );


        return (
            roleChanged
            ||
            statusChanged
        );

    }


    function updateEditSaveState() {

        if (!editSaveButton) {
            return;
        }


        editSaveButton.disabled =
            (
                editBusy
                ||
                !hasEditChanges()
            );

    }


    function fillUserModal(
        data
    ) {

        activeUserData =
            data;


        originalRole =
            data.role
            ||
            "user";


        pendingStatusAction =
            "none";


        renderEditAvatar(
            data
        );


        setText(
            editName,
            data.name
        );


        setText(
            editEmail,
            data.email
        );


        if (
            editUsername
        ) {

            editUsername.textContent =
                data.username
                    ? `@${data.username}`
                    : "—";

        }


        setText(
            editReadonlyName,
            data.name
        );


        setText(
            editEmployeeId,
            data.employee_id
        );


        setText(
            editPhone,
            data.phone_number
        );


        setText(
            editDepartment,
            data.department
        );


        setText(
            editJobTitle,
            data.job_title
        );


        setText(
            editShift,
            data.shift
        );


        if (
            editRole
        ) {

            editRole.value =
                originalRole;


            editRole.disabled =
                (
                    !data.can_edit_role
                );

        }


        if (
            editRoleHelp
        ) {

            editRoleHelp.textContent =
                data.can_edit_role

                    ? (
                        "Role changes take effect immediately after saving."
                    )

                    : (
                        "You cannot change your own SuperAdmin role."
                    );

        }


        if (
            editProtection
        ) {

            editProtection.hidden =
                (
                    !data.is_self
                );

        }


        updateStatusControl();

        updateEditSaveState();

    }


    async function openUserEditModal(
        button
    ) {

        if (
            !userModal
            ||
            !userModalLoading
            ||
            !userModalContent
        ) {
            return;
        }


        const editUrl =
            button.dataset
                .editUrl;


        if (!editUrl) {
            return;
        }


        activeEditButton =
            button;


        activeUserData =
            null;


        originalRole =
            "";


        pendingStatusAction =
            "none";


        setUserModalError(
            ""
        );


        userModalLoading.hidden =
            false;


        userModalContent.hidden =
            true;


        if (
            editSaveButton
        ) {

            editSaveButton.disabled =
                true;

        }


        userModal.hidden =
            false;


        document.body.style.overflow =
            "hidden";


        button.disabled =
            true;


        try {

            const response =
                await fetch(
                    editUrl,
                    {
                        method:
                            "GET",

                        credentials:
                            "same-origin",

                        headers: {
                            "Accept":
                                "application/json"
                        }
                    }
                );


            const result =
                await response.json();


            if (
                !response.ok
                ||
                !result.ok
            ) {

                throw new Error(
                    result.message
                    ||
                    "Unable to load this user."
                );

            }


            fillUserModal(
                result.user
            );


            userModalLoading.hidden =
                true;


            userModalContent.hidden =
                false;

        }

        catch (
            error
        ) {

            userModalLoading.hidden =
                true;


            userModalContent.hidden =
                false;


            setUserModalError(
                error.message
                ||
                "Unable to load this user."
            );

        }

        finally {

            button.disabled =
                false;

        }

    }


    function closeUserEditModal() {

        if (
            editBusy
        ) {
            return;
        }


        if (
            userConfirm
            &&
            !userConfirm.hidden
        ) {
            return;
        }


        if (
            userModal
        ) {

            userModal.hidden =
                true;

        }


        document.body.style.overflow =
            "";


        activeEditButton =
            null;


        activeUserData =
            null;


        originalRole =
            "";


        pendingStatusAction =
            "none";


        setUserModalError(
            ""
        );

    }


    function resetUserConfirmPassword() {

        if (
            userConfirmPassword
        ) {

            userConfirmPassword.value =
                "";


            userConfirmPassword.type =
                "password";

        }


        if (
            userConfirmPasswordError
        ) {

            userConfirmPasswordError.textContent =
                "";

        }


        if (
            userConfirmPasswordEye
        ) {

            userConfirmPasswordEye.setAttribute(
                "name",
                "eye"
            );

        }


        if (
            userConfirmPasswordToggle
        ) {

            userConfirmPasswordToggle.setAttribute(
                "aria-label",
                "Show password"
            );

        }

    }


    function updateUserConfirmSaveState() {

        if (
            !userConfirmSave
        ) {
            return;
        }


        if (
            editBusy
        ) {

            userConfirmSave.disabled =
                true;

            return;

        }


        const roleChanged =
            (
                editRole
                &&
                editRole.value
                !==
                originalRole
            );


        const requiresPassword =
            (
                roleChanged
                ||
                pendingStatusAction
                !==
                "none"
            );


        if (
            requiresPassword
        ) {

            userConfirmSave.disabled =
                !(
                    userConfirmPassword
                    &&
                    userConfirmPassword.value.trim()
                );

            return;

        }


        userConfirmSave.disabled =
            false;

    }


    function showUserConfirm() {

        if (
            !userConfirm
            ||
            !activeUserData
            ||
            !hasEditChanges()
        ) {
            return;
        }


        const changes =
            [];


        const roleChanged =
            (
                editRole
                &&
                editRole.value
                !==
                originalRole
            );


        const requiresPassword =
            (
                roleChanged
                ||
                pendingStatusAction
                !==
                "none"
            );


        if (
            editRole
            &&
            editRole.value
            !==
            originalRole
        ) {

            changes.push(
                (
                    `Access role: `
                    +
                    `${statusLabel(originalRole)} → `
                    +
                    `${statusLabel(editRole.value)}`
                )
            );

        }


        if (
            pendingStatusAction
            !==
            "none"
        ) {

            const nextStatus =
                statusDestination(
                    activeUserData.status,
                    pendingStatusAction
                );


            changes.push(
                (
                    `Account status: `
                    +
                    `${statusLabel(activeUserData.status)} → `
                    +
                    `${statusLabel(nextStatus)}`
                )
            );

        }


        resetUserConfirmPassword();


        if (
            requiresPassword
        ) {

            if (
                userConfirmTitle
            ) {

                if (
                    roleChanged
                    &&
                    pendingStatusAction
                    !==
                    "none"
                ) {

                    userConfirmTitle.textContent =
                        "Confirm access changes";

                }

                else if (
                    roleChanged
                ) {

                    userConfirmTitle.textContent =
                        "Confirm role change";

                }

                else if (
                    pendingStatusAction
                    ===
                    "disable"
                ) {

                    userConfirmTitle.textContent =
                        "Disable this account?";

                }

                else if (
                    pendingStatusAction
                    ===
                    "reactivate"
                ) {

                    userConfirmTitle.textContent =
                        "Reactivate this account?";

                }

                else if (
                    pendingStatusAction
                    ===
                    "unlock"
                ) {

                    userConfirmTitle.textContent =
                        "Unlock this account?";

                }

                else {

                    userConfirmTitle.textContent =
                        "Confirm access changes";

                }

            }


            if (
                userConfirmPasswordWrap
            ) {

                userConfirmPasswordWrap.hidden =
                    false;

            }


            if (
                userConfirmSave
            ) {

                userConfirmSave.textContent =
                    "Confirm Changes";

            }

        }

        else {

            if (
                userConfirmTitle
            ) {

                userConfirmTitle.textContent =
                    "Save user changes?";

            }


            if (
                userConfirmPasswordWrap
            ) {

                userConfirmPasswordWrap.hidden =
                    true;

            }


            if (
                userConfirmSave
            ) {

                userConfirmSave.textContent =
                    "Confirm & Save";

            }

        }


        if (
            userConfirmMessage
        ) {

            userConfirmMessage.textContent =
                (
                    changes.join(
                        " · "
                    )
                    ||
                    "The selected access changes will be applied."
                );

        }


        updateUserConfirmSaveState();


        userConfirm.hidden =
            false;


        if (
            requiresPassword
            &&
            userConfirmPassword
        ) {

            window.setTimeout(
                () => {

                    userConfirmPassword.focus();

                },
                60
            );

        }

    }


    function hideUserConfirm() {

        if (
            editBusy
        ) {
            return;
        }


        if (
            userConfirm
        ) {

            userConfirm.hidden =
                true;

        }


        resetUserConfirmPassword();

    }


    async function saveUserAccess() {

        if (
            !activeEditButton
            ||
            !activeUserData
            ||
            !editRole
        ) {
            return;
        }


        const updateUrl =
            activeEditButton.dataset
                .updateUrl;


        if (!updateUrl) {
            return;
        }


        const roleChanged =
            (
                editRole
                &&
                editRole.value
                !==
                originalRole
            );


        const requiresPassword =
            (
                roleChanged
                ||
                pendingStatusAction
                !==
                "none"
            );


        const superadminPassword =
            requiresPassword
                ? (
                    userConfirmPassword
                        ?.value
                        ??
                        ""
                )
                : "";


        if (
            requiresPassword
            &&
            !superadminPassword.trim()
        ) {

            if (
                userConfirmPasswordError
            ) {

                userConfirmPasswordError.textContent =
                    "Enter your SuperAdmin password.";

            }


            userConfirmPassword?.focus();

            updateUserConfirmSaveState();

            return;

        }


        editBusy =
            true;


        const confirmationLabel =
            requiresPassword
                ? "Confirm Changes"
                : "Confirm & Save";


        if (
            userConfirmSave
        ) {

            userConfirmSave.disabled =
                true;


            userConfirmSave.textContent =
                "Saving...";

        }


        if (
            userConfirmPasswordError
        ) {

            userConfirmPasswordError.textContent =
                "";

        }


        setUserModalError(
            ""
        );


        try {

            const response =
                await fetch(
                    updateUrl,
                    {
                        method:
                            "POST",

                        credentials:
                            "same-origin",

                        headers: {
                            "Content-Type":
                                "application/json",

                            "Accept":
                                "application/json",

                            "X-CSRFToken":
                                getCsrfToken()
                        },

                        body:
                            JSON.stringify({
                                role:
                                    editRole.value,

                                status_action:
                                    pendingStatusAction,

                                superadmin_password:
                                    superadminPassword
                            })
                    }
                );


            const result =
                await response.json();


            if (
                !response.ok
                ||
                !result.ok
            ) {

                if (
                    requiresPassword
                    &&
                    (
                        result.code
                        ===
                        "invalid_superadmin_password"
                        ||
                        result.code
                        ===
                        "superadmin_password_required"
                    )
                ) {

                    if (
                        userConfirmPasswordError
                    ) {

                        userConfirmPasswordError.textContent =
                            (
                                result.message
                                ||
                                "Incorrect SuperAdmin password."
                            );

                    }


                    if (
                        userConfirmPassword
                    ) {

                        userConfirmPassword.value =
                            "";


                        userConfirmPassword.focus();

                    }


                    return;

                }


                throw new Error(
                    result.message
                    ||
                    "Unable to save user changes."
                );

            }


            resetUserConfirmPassword();


            if (
                userConfirm
            ) {

                userConfirm.hidden =
                    true;

            }


            if (
                userModal
            ) {

                userModal.hidden =
                    true;

            }


            document.body.style.overflow =
                "";


            window.setTimeout(
                () => {

                    window.location.reload();

                },
                180
            );

        }

        catch (
            error
        ) {

            if (
                userConfirm
            ) {

                userConfirm.hidden =
                    true;

            }


            resetUserConfirmPassword();


            setUserModalError(
                error.message
                ||
                "Unable to save user changes."
            );

        }

        finally {

            editBusy =
                false;


            if (
                userConfirmSave
            ) {

                userConfirmSave.textContent =
                    confirmationLabel;

            }


            updateUserConfirmSaveState();

            updateEditSaveState();

        }

    }


    /* =====================================================
       USER EDIT EVENTS
       ===================================================== */

    editButtons.forEach(
        (
            button
        ) => {

            button.addEventListener(
                "click",
                () => {

                    openUserEditModal(
                        button
                    );

                }
            );

        }
    );


    userModalCloseButtons.forEach(
        (
            button
        ) => {

            button.addEventListener(
                "click",
                closeUserEditModal
            );

        }
    );


    userModal?.addEventListener(
        "click",
        (
            event
        ) => {

            if (
                event.target
                ===
                userModal
            ) {

                closeUserEditModal();

            }

        }
    );


    editRole?.addEventListener(
        "change",
        () => {

            updateEditSaveState();

        }
    );


    editStatusAction?.addEventListener(
        "click",
        () => {

            if (
                !activeUserData
                ||
                !activeUserData.can_change_status
            ) {
                return;
            }


            if (
                pendingStatusAction
                !==
                "none"
            ) {

                pendingStatusAction =
                    "none";

            }

            else {

                pendingStatusAction =
                    actionForStatus(
                        activeUserData.status
                    )
                        .action;

            }


            updateStatusControl();

            updateEditSaveState();

        }
    );


    editSaveButton?.addEventListener(
        "click",
        showUserConfirm
    );


    userConfirmCancel?.addEventListener(
        "click",
        hideUserConfirm
    );


    userConfirmSave?.addEventListener(
        "click",
        saveUserAccess
    );



    userConfirmPassword?.addEventListener(
        "input",
        () => {

            if (
                userConfirmPasswordError
            ) {

                userConfirmPasswordError.textContent =
                    "";

            }


            updateUserConfirmSaveState();

        }
    );


    userConfirmPassword?.addEventListener(
        "keydown",
        (
            event
        ) => {

            if (
                event.key
                !==
                "Enter"
            ) {
                return;
            }


            if (
                userConfirmSave
                &&
                !userConfirmSave.disabled
            ) {

                event.preventDefault();

                saveUserAccess();

            }

        }
    );


    userConfirmPasswordToggle?.addEventListener(
        "click",
        () => {

            if (
                !userConfirmPassword
            ) {
                return;
            }


            const isHidden =
                (
                    userConfirmPassword.type
                    ===
                    "password"
                );


            userConfirmPassword.type =
                isHidden
                    ? "text"
                    : "password";


            if (
                userConfirmPasswordEye
            ) {

                userConfirmPasswordEye.setAttribute(
                    "name",
                    isHidden
                        ? "eye-slash"
                        : "eye"
                );

            }


            userConfirmPasswordToggle.setAttribute(
                "aria-label",
                isHidden
                    ? "Hide password"
                    : "Show password"
            );


            userConfirmPassword.focus();

        }
    );


    userConfirm?.addEventListener(
        "click",
        (
            event
        ) => {

            if (
                event.target
                ===
                userConfirm
            ) {

                hideUserConfirm();

            }

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


            if (
                userConfirm
                &&
                !userConfirm.hidden
            ) {

                hideUserConfirm();

                return;

            }


            if (
                userModal
                &&
                !userModal.hidden
            ) {

                closeUserEditModal();

            }

        }
    );


    /* =====================================================
       INITIAL
       ===================================================== */

    refreshProcessedRows();

    updateSortButtonUI();

    render();


})();
