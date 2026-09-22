/* =========================================================
   BIKA
   WORK INFORMATION REQUESTS
   ========================================================= */

(() => {

    "use strict";


    const page =
        document.querySelector(
            "[data-work-requests-page]"
        );


    if (!page) {
        return;
    }



    /* =====================================================
       SEARCH
       ===================================================== */

    const searchInput =
        page.querySelector(
            "[data-work-search]"
        );


    const rows =
        Array.from(
            page.querySelectorAll(
                "[data-work-row]"
            )
        );


    const visibleCount =
        page.querySelector(
            "[data-visible-count]"
        );


    const resultText =
        page.querySelector(
            "[data-table-result-text]"
        );



    function updateSearch() {

        if (!searchInput) {
            return;
        }


        const query =
            String(
                searchInput.value
                ||
                ""
            )
            .trim()
            .toLowerCase();


        let visible =
            0;


        rows.forEach(
            (
                row
            ) => {

                const haystack =
                    String(
                        row.dataset.searchText
                        ||
                        ""
                    )
                    .toLowerCase();


                const show =
                    (
                        !query
                        ||
                        haystack.includes(
                            query
                        )
                    );


                row.hidden =
                    !show;


                if (show) {

                    visible +=
                        1;

                }

            }
        );


        if (
            visibleCount
        ) {

            visibleCount.textContent =
                String(
                    visible
                );

        }


        if (
            resultText
        ) {

            if (
                query
            ) {

                resultText.textContent =
                    (
                        `${visible} matching `
                        +
                        (
                            visible === 1
                                ?
                                "request"
                                :
                                "requests"
                        )
                    );

            }

            else {

                resultText.textContent =
                    (
                        `Showing ${visible} of `
                        +
                        `${rows.length} requests`
                    );

            }

        }

    }



    if (
        searchInput
    ) {

        searchInput.addEventListener(
            "input",
            updateSearch
        );

    }



    /* =====================================================
       MODAL HELPERS
       ===================================================== */

    let currentModal =
        null;


    let lastTrigger =
        null;



    function lockPage() {

        document.documentElement.style.overflow =
            "hidden";

    }



    function unlockPage() {

        document.documentElement.style.overflow =
            "";

    }



    function removeReviewQuery() {

        const url =
            new URL(
                window.location.href
            );


        if (
            !url.searchParams.has(
                "review"
            )
        ) {

            return;

        }


        url.searchParams.delete(
            "review"
        );


        window.history.replaceState(
            {},
            "",
            (
                url.pathname
                +
                url.search
                +
                url.hash
            )
        );

    }



    function openModal(
        requestId,
        trigger = null
    ) {

        const modal =
            page.querySelector(
                `[data-work-modal="${requestId}"]`
            );


        if (!modal) {
            return;
        }


        if (
            currentModal
            &&
            currentModal !== modal
        ) {

            closeModal(
                false
            );

        }


        lastTrigger =
            trigger;


        currentModal =
            modal;


        modal.hidden =
            false;


        lockPage();


        window.requestAnimationFrame(
            () => {

                modal.classList.add(
                    "is-open"
                );

            }
        );

    }



    function closeModal(
        restoreFocus = true
    ) {

        if (!currentModal) {
            return;
        }


        const closingModal =
            currentModal;


        currentModal =
            null;


        closingModal.classList.remove(
            "is-open"
        );


        window.setTimeout(
            () => {

                closingModal.hidden =
                    true;


                if (
                    !document.querySelector(
                        ".wir-modal-backdrop.is-open"
                    )
                ) {

                    unlockPage();

                }


                if (
                    restoreFocus
                    &&
                    lastTrigger
                ) {

                    lastTrigger.focus();

                }

            },
            170
        );


        removeReviewQuery();

    }



    /* =====================================================
       REVIEW BUTTONS
       ===================================================== */

    page
        .querySelectorAll(
            "[data-work-review-button]"
        )
        .forEach(
            (
                button
            ) => {

                button.addEventListener(
                    "click",
                    () => {

                        openModal(
                            button.dataset.requestId,
                            button
                        );

                    }
                );

            }
        );



    /* =====================================================
       CLOSE BUTTONS
       ===================================================== */

    page
        .querySelectorAll(
            "[data-work-modal-close]"
        )
        .forEach(
            (
                button
            ) => {

                button.addEventListener(
                    "click",
                    () => {

                        closeModal();

                    }
                );

            }
        );



    /* =====================================================
       BACKDROP CLICK
       ===================================================== */

    page
        .querySelectorAll(
            "[data-work-modal]"
        )
        .forEach(
            (
                backdrop
            ) => {

                backdrop.addEventListener(
                    "click",
                    (
                        event
                    ) => {

                        if (
                            event.target
                            !==
                            backdrop
                        ) {

                            return;

                        }


                        closeModal();

                    }
                );

            }
        );



    /* =====================================================
       ESC
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


            const confirmation =
                page.querySelector(
                    "[data-approve-confirm]"
                );


            if (
                confirmation
                &&
                !confirmation.hidden
            ) {

                confirmation.hidden =
                    true;

                return;

            }


            if (
                currentModal
            ) {

                closeModal();

            }

        }
    );



    /* =====================================================
       REJECTION REASON
       ===================================================== */

    page
        .querySelectorAll(
            "[data-reject-form]"
        )
        .forEach(
            (
                form
            ) => {

                const textarea =
                    form.querySelector(
                        "[data-rejection-reason]"
                    );


                const button =
                    form.querySelector(
                        "[data-reject-button]"
                    );


                const count =
                    form.querySelector(
                        "[data-reason-count]"
                    );


                if (
                    !textarea
                    ||
                    !button
                ) {

                    return;

                }



                function updateReject() {

                    const value =
                        textarea.value;


                    const trimmed =
                        value.trim();


                    if (
                        count
                    ) {

                        count.textContent =
                            (
                                `${value.length} / 1000`
                            );

                    }


                    button.disabled =
                        (
                            trimmed.length
                            <
                            3
                        );

                }



                textarea.addEventListener(
                    "input",
                    updateReject
                );


                updateReject();

            }
        );



    /* =====================================================
       APPROVAL CONFIRMATION
       ===================================================== */

    const confirmation =
        page.querySelector(
            "[data-approve-confirm]"
        );


    const confirmApproveButton =
        page.querySelector(
            "[data-approve-confirm-button]"
        );


    const cancelApproveButton =
        page.querySelector(
            "[data-approve-cancel]"
        );


    let pendingApproveForm =
        null;



    page
        .querySelectorAll(
            "[data-approve-open]"
        )
        .forEach(
            (
                button
            ) => {

                button.addEventListener(
                    "click",
                    () => {

                        const requestId =
                            button.dataset.approveOpen;


                        pendingApproveForm =
                            page.querySelector(
                                `[data-approve-form="${requestId}"]`
                            );


                        if (
                            !pendingApproveForm
                            ||
                            !confirmation
                        ) {

                            return;

                        }


                        confirmation.hidden =
                            false;

                    }
                );

            }
        );



    if (
        cancelApproveButton
    ) {

        cancelApproveButton.addEventListener(
            "click",
            () => {

                pendingApproveForm =
                    null;


                if (
                    confirmation
                ) {

                    confirmation.hidden =
                        true;

                }

            }
        );

    }



    if (
        confirmation
    ) {

        confirmation.addEventListener(
            "click",
            (
                event
            ) => {

                if (
                    event.target
                    !==
                    confirmation
                ) {

                    return;

                }


                pendingApproveForm =
                    null;


                confirmation.hidden =
                    true;

            }
        );

    }



    if (
        confirmApproveButton
    ) {

        confirmApproveButton.addEventListener(
            "click",
            () => {

                if (
                    !pendingApproveForm
                ) {

                    return;

                }


                confirmApproveButton.disabled =
                    true;


                confirmApproveButton.textContent =
                    "Approving...";


                HTMLFormElement
                    .prototype
                    .submit
                    .call(
                        pendingApproveForm
                    );

            }
        );

    }



    /* =====================================================
       AUTO OPEN ?review=
       ===================================================== */

    const currentUrl =
        new URL(
            window.location.href
        );


    const reviewId =
        currentUrl.searchParams.get(
            "review"
        );


    if (
        reviewId
    ) {

        const safeId =
            (
                window.CSS
                &&
                CSS.escape
            )
            ?
            CSS.escape(
                reviewId
            )
            :
            reviewId.replace(
                /["\\]/g,
                ""
            );


        const trigger =
            page.querySelector(
                (
                    `[data-work-review-button]`
                    +
                    `[data-request-id="${safeId}"]`
                )
            );


        if (
            trigger
        ) {

            openModal(
                reviewId,
                trigger
            );

        }

    }


})();