/* =========================================================
   BIKA
   USER NOTIFICATION PREFERENCES
   ========================================================= */

(() => {

    "use strict";


    const container =
        document.querySelector(
            "[data-notification-preferences]"
        );


    if (!container) {
        return;
    }



    /* =====================================================
       SAVE URL
       ===================================================== */

    const saveUrl =
        container.dataset.saveUrl;


    if (!saveUrl) {

        console.error(
            "[BIKA] Notification preference save URL is missing."
        );


        return;

    }



    /* =====================================================
       CSRF
       ===================================================== */

    const csrfMeta =
        document.querySelector(
            'meta[name="csrf-token"]'
        );


    const csrfToken =
        csrfMeta
            ?
            csrfMeta.content
            :
            "";



    /* =====================================================
       TOGGLES
       ===================================================== */

    const toggles =
        Array.from(
            container.querySelectorAll(
                "[data-notification-preference]"
            )
        );



    /* =====================================================
       SAVE ONE PREFERENCE
       ===================================================== */

    async function savePreference(
        input
    ) {

        const preference =
            input.dataset
                .notificationPreference;


        if (!preference) {
            return;
        }


        const newValue =
            Boolean(
                input.checked
            );


        /*
         * Remember previous value so we can
         * restore it if request fails.
         */

        const previousValue =
            !newValue;


        input.disabled =
            true;


        try {

            const response =
                await fetch(
                    saveUrl,
                    {

                        method:
                            "POST",

                        credentials:
                            "same-origin",

                        headers: {

                            "Accept":
                                "application/json",

                            "Content-Type":
                                "application/json",

                            "X-Requested-With":
                                "XMLHttpRequest",

                            "X-CSRFToken":
                                csrfToken

                        },


                        body:
                            JSON.stringify(
                                {

                                    preference:
                                        preference,

                                    enabled:
                                        newValue

                                }
                            )

                    }
                );



            const data =
                await response.json();



            if (
                !response.ok
                ||
                data.ok !== true
            ) {

                throw new Error(
                    data.message
                    ||
                    "Unable to save preference."
                );

            }



            /* =================================================
               BACKEND IS SOURCE OF TRUTH
               ================================================= */

            if (
                preference
                ===
                "email_notifications"
            ) {

                input.checked =
                    Boolean(
                        data.email_notifications
                    );

            }


            else if (
                preference
                ===
                "in_app_alerts"
            ) {

                input.checked =
                    Boolean(
                        data.in_app_alerts
                    );

            }


            showPreferenceToast(
                "Preference saved"
            );

        }

        catch (
            error
        ) {

            console.error(
                "[BIKA] Notification preference save failed:",
                error
            );


            /*
             * Restore old switch position.
             */

            input.checked =
                previousValue;


            showPreferenceToast(
                "Unable to save preference",
                true
            );

        }

        finally {

            input.disabled =
                false;

        }

    }



    /* =====================================================
       BIND
       ===================================================== */

    toggles.forEach(
        (
            input
        ) => {

            input.addEventListener(
                "change",
                () => {

                    savePreference(
                        input
                    );

                }
            );

        }
    );



    /* =====================================================
       SMALL TOAST
       ===================================================== */

    function showPreferenceToast(
        message,
        isError = false
    ) {

        const existing =
            document.querySelector(
                "[data-preference-toast]"
            );


        if (
            existing
        ) {

            existing.remove();

        }


        const toast =
            document.createElement(
                "div"
            );


        toast.setAttribute(
            "data-preference-toast",
            ""
        );


        toast.style.position =
            "fixed";


        toast.style.top =
            "82px";


        toast.style.right =
            "30px";


        toast.style.zIndex =
            "2800";


        toast.style.padding =
            "10px 14px";


        toast.style.borderRadius =
            "11px";


        toast.style.background =
            "var(--surface-strong, #FFFFFF)";


        toast.style.boxShadow =
            "0 4px 16px #E8E8E8";


        toast.style.border =
            isError
                ?
                "1px solid rgba(181,72,88,.30)"
                :
                "1px solid rgba(128,163,119,.28)";


        toast.style.color =
            "var(--text-primary, #242424)";


        toast.style.fontSize =
            "11px";


        toast.style.opacity =
            "0";


        toast.style.transform =
            "translateY(-5px)";


        toast.style.transition =
            "opacity 160ms ease, transform 160ms ease";


        toast.textContent =
            message;


        document.body.appendChild(
            toast
        );


        window.requestAnimationFrame(
            () => {

                toast.style.opacity =
                    "1";


                toast.style.transform =
                    "translateY(0)";

            }
        );


        window.setTimeout(
            () => {

                toast.style.opacity =
                    "0";


                toast.style.transform =
                    "translateY(-5px)";


                window.setTimeout(
                    () => {

                        toast.remove();

                    },
                    180
                );

            },
            1800
        );

    }

})();