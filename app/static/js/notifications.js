/* =========================================================
   BIKA NOTIFICATION DROPDOWN
   ========================================================= */

(() => {

    "use strict";


    const root =
        document.querySelector(
            "[data-notification-root]"
        );


    if (!root) {
        return;
    }


    const toggleButton =
        root.querySelector(
            "[data-notification-toggle]"
        );


    const dropdown =
        root.querySelector(
            "[data-notification-dropdown]"
        );


    const badge =
        root.querySelector(
            "[data-notification-badge]"
        );


    const summary =
        root.querySelector(
            "[data-notification-summary]"
        );


    const loading =
        root.querySelector(
            "[data-notification-loading]"
        );


    const list =
        root.querySelector(
            "[data-notification-list]"
        );


    const empty =
        root.querySelector(
            "[data-notification-empty]"
        );


    const readAllButton =
        root.querySelector(
            "[data-notification-read-all]"
        );


    const apiUrl =
        root.dataset.notificationApi;


    const readAllUrl =
        root.dataset.notificationReadAllUrl;


    const csrfMeta =
        document.querySelector(
            'meta[name="csrf-token"]'
        );


    const csrfToken =
        csrfMeta
            ? csrfMeta.content
            : "";


    let isOpen =
        false;


    let loadingNow =
        false;



    /* =====================================================
       HTML ESCAPE
       ===================================================== */

    function escapeHtml(
        value
    ) {

        const element =
            document.createElement(
                "div"
            );


        element.textContent =
            String(
                value
                ??
                ""
            );


        return element.innerHTML;

    }



    /* =====================================================
       RELATIVE TIME
       ===================================================== */

    function relativeTime(
        isoValue
    ) {

        if (!isoValue) {
            return "";
        }


        const date =
            new Date(
                isoValue
            );


        if (
            Number.isNaN(
                date.getTime()
            )
        ) {
            return "";
        }


        const now =
            new Date();


        const differenceSeconds =
            Math.max(
                0,
                Math.floor(
                    (
                        now.getTime()
                        -
                        date.getTime()
                    )
                    /
                    1000
                )
            );


        if (
            differenceSeconds
            <
            60
        ) {

            return "Just now";

        }


        const minutes =
            Math.floor(
                differenceSeconds
                /
                60
            );


        if (
            minutes
            <
            60
        ) {

            return (
                `${minutes} min ago`
            );

        }


        const hours =
            Math.floor(
                minutes
                /
                60
            );


        if (
            hours
            <
            24
        ) {

            return (
                hours === 1
                    ? "1 hour ago"
                    : `${hours} hours ago`
            );

        }


        const days =
            Math.floor(
                hours
                /
                24
            );


        if (
            days
            <
            7
        ) {

            return (
                days === 1
                    ? "Yesterday"
                    : `${days} days ago`
            );

        }


        return date.toLocaleDateString(
            undefined,
            {
                day:
                    "2-digit",

                month:
                    "short",

                year:
                    "numeric"
            }
        );

    }



    /* =====================================================
       BADGE
       ===================================================== */

    function updateBadge(
        unreadCount
    ) {

        const count =
            Number(
                unreadCount
                ||
                0
            );


        if (
            count <= 0
        ) {

            badge.hidden =
                true;


            badge.textContent =
                "0";


            return;

        }


        badge.hidden =
            false;


        badge.textContent =
            count > 99
                ? "99+"
                : String(
                    count
                );

    }



    /* =====================================================
       SUMMARY
       ===================================================== */

    function updateSummary(
        unreadCount
    ) {

        const count =
            Number(
                unreadCount
                ||
                0
            );


        if (
            count <= 0
        ) {

            summary.textContent =
                "You're all caught up";


            readAllButton.hidden =
                true;


            return;

        }


        summary.textContent =
            (
                count === 1
                    ? "1 unread notification"
                    : `${count} unread notifications`
            );


        readAllButton.hidden =
            false;

    }



    /* =====================================================
       ICON
       ===================================================== */

    function iconMarkup(
        type
    ) {

        if (
            type
            ===
            "work_info_request_approved"
        ) {

            return `
                <svg
                    viewBox="0 0 24 24"
                    aria-hidden="true"
                >
                    <circle
                        cx="12"
                        cy="12"
                        r="8"
                    ></circle>

                    <path
                        d="M8.5 12L11 14.5L15.5 9.5"
                    ></path>
                </svg>
            `;

        }


        if (
            type
            ===
            "work_info_request_rejected"
        ) {

            return `
                <svg
                    viewBox="0 0 24 24"
                    aria-hidden="true"
                >
                    <circle
                        cx="12"
                        cy="12"
                        r="8"
                    ></circle>

                    <path
                        d="M9 9L15 15"
                    ></path>

                    <path
                        d="M15 9L9 15"
                    ></path>
                </svg>
            `;

        }


        if (
            type
            ===
            "work_info_request_submitted"
        ) {

            return `
                <svg
                    viewBox="0 0 24 24"
                    aria-hidden="true"
                >
                    <circle
                        cx="9"
                        cy="8"
                        r="3"
                    ></circle>

                    <path
                        d="
                            M3.5 19
                            C4.2 15.7
                            6.1 14
                            9 14
                            C11.9 14
                            13.8 15.7
                            14.5 19
                        "
                    ></path>

                    <path
                        d="M16 8H21"
                    ></path>

                    <path
                        d="M18.5 5.5V10.5"
                    ></path>
                </svg>
            `;

        }


        return `
            <svg
                viewBox="0 0 24 24"
                aria-hidden="true"
            >
                <path
                    d="
                        M6 16
                        H18
                        L17 14
                        V10
                        C17 7.2
                        15 5
                        12 5
                        C9 5
                        7 7.2
                        7 10
                        V14
                        Z
                    "
                ></path>

                <path
                    d="
                        M10 19
                        C10.5 20
                        11.1 20.5
                        12 20.5
                        C12.9 20.5
                        13.5 20
                        14 19
                    "
                ></path>
            </svg>
        `;

    }



    /* =====================================================
       RENDER
       ===================================================== */

    function renderNotifications(
        notifications
    ) {

        list.innerHTML =
            "";


        if (
            !Array.isArray(
                notifications
            )
            ||
            notifications.length
            ===
            0
        ) {

            list.hidden =
                true;


            empty.hidden =
                false;


            return;

        }


        empty.hidden =
            true;


        list.hidden =
            false;


        notifications.forEach(
            (
                notification
            ) => {

                const item =
                    document.createElement(
                        "a"
                    );


                item.href =
                    notification.open_url;


                item.className =
                    "app-notification-item";


                if (
                    !notification.is_read
                ) {

                    item.classList.add(
                        "is-unread"
                    );

                }


                const title =
                    escapeHtml(
                        notification.title
                    );


                const message =
                    escapeHtml(
                        notification.message
                    );


                const time =
                    escapeHtml(
                        relativeTime(
                            notification.created_at
                        )
                    );


                item.innerHTML = `

                    <span
                        class="app-notification-item-icon"
                    >
                        ${iconMarkup(
                            notification.type
                        )}
                    </span>


                    <span
                        class="app-notification-item-copy"
                    >

                        <strong>
                            ${title}
                        </strong>

                        <span
                            class="app-notification-message"
                        >
                            ${message}
                        </span>

                        <small>
                            ${time}
                        </small>

                    </span>


                    ${
                        notification.is_read
                            ?
                            ""
                            :
                            `
                                <span
                                    class="app-notification-unread-dot"
                                    aria-label="Unread"
                                ></span>
                            `
                    }

                `;


                list.appendChild(
                    item
                );

            }
        );

    }



    /* =====================================================
       LOAD
       ===================================================== */

    async function loadNotifications() {

        if (
            loadingNow
        ) {
            return;
        }


        if (!apiUrl) {
            return;
        }


        loadingNow =
            true;


        loading.hidden =
            false;


        list.hidden =
            true;


        empty.hidden =
            true;


        try {

            const response =
                await fetch(
                    apiUrl,
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

                        }

                    }
                );


            if (!response.ok) {

                throw new Error(
                    (
                        "Unable to load notifications "
                        +
                        `(${response.status})`
                    )
                );

            }


            const data =
                await response.json();


            if (
                data.ok
                !==
                true
            ) {

                throw new Error(
                    "Notification API returned an error."
                );

            }


            updateBadge(
                data.unread_count
            );


            updateSummary(
                data.unread_count
            );


            renderNotifications(
                data.notifications
            );

        }

        catch (
            error
        ) {

            console.error(
                "[BIKA Notifications]",
                error
            );


            list.hidden =
                true;


            empty.hidden =
                false;


            empty.innerHTML = `

                <strong>
                    Unable to load notifications
                </strong>

                <span>
                    Please try again.
                </span>

            `;

        }

        finally {

            loading.hidden =
                true;


            loadingNow =
                false;

        }

    }



    /* =====================================================
       OPEN
       ===================================================== */

    function openDropdown() {

        isOpen =
            true;


        dropdown.hidden =
            false;


        toggleButton.setAttribute(
            "aria-expanded",
            "true"
        );


        root.classList.add(
            "is-open"
        );


        loadNotifications();

    }



    /* =====================================================
       CLOSE
       ===================================================== */

    function closeDropdown() {

        isOpen =
            false;


        dropdown.hidden =
            true;


        toggleButton.setAttribute(
            "aria-expanded",
            "false"
        );


        root.classList.remove(
            "is-open"
        );

    }



    /* =====================================================
       TOGGLE
       ===================================================== */

    toggleButton.addEventListener(
        "click",
        (
            event
        ) => {

            event.preventDefault();

            event.stopPropagation();


            if (
                isOpen
            ) {

                closeDropdown();

            }

            else {

                openDropdown();

            }

        }
    );



    /* =====================================================
       PREVENT INNER CLICK FROM CLOSING
       ===================================================== */

    dropdown.addEventListener(
        "click",
        (
            event
        ) => {

            event.stopPropagation();

        }
    );



    /* =====================================================
       CLICK OUTSIDE
       ===================================================== */

    document.addEventListener(
        "click",
        (
            event
        ) => {

            if (
                !isOpen
            ) {
                return;
            }


            if (
                root.contains(
                    event.target
                )
            ) {
                return;
            }


            closeDropdown();

        }
    );



    /* =====================================================
       ESCAPE
       ===================================================== */

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
                !isOpen
            ) {
                return;
            }


            closeDropdown();


            toggleButton.focus();

        }
    );



    /* =====================================================
       MARK ALL READ
       ===================================================== */

    readAllButton.addEventListener(
        "click",
        async (
            event
        ) => {

            event.preventDefault();

            event.stopPropagation();


            if (!readAllUrl) {
                return;
            }


            readAllButton.disabled =
                true;


            try {

                const response =
                    await fetch(
                        readAllUrl,
                        {

                            method:
                                "POST",

                            credentials:
                                "same-origin",

                            headers: {

                                "Accept":
                                    "application/json",

                                "X-Requested-With":
                                    "XMLHttpRequest",

                                "X-CSRFToken":
                                    csrfToken

                            }

                        }
                    );


                if (!response.ok) {

                    throw new Error(
                        (
                            "Unable to mark notifications "
                            +
                            `(${response.status})`
                        )
                    );

                }


                const data =
                    await response.json();


                if (
                    data.ok
                    !==
                    true
                ) {

                    throw new Error(
                        "Unable to mark all notifications as read."
                    );

                }


                await loadNotifications();

            }

            catch (
                error
            ) {

                console.error(
                    "[BIKA Notifications]",
                    error
                );

            }

            finally {

                readAllButton.disabled =
                    false;

            }

        }
    );



    /* =====================================================
       INITIAL BADGE
       ===================================================== */

    loadNotifications();

})();