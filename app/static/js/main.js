/* =========================================================
   BIKA MAIN.JS
   ========================================================= */

(() => {

    "use strict";


    /* =====================================================
       THEME
       ===================================================== */

    const root =
        document.documentElement;


    const themeButtons =
        Array.from(
            document.querySelectorAll(
                "[data-theme-choice]"
            )
        );


    function getCurrentTheme() {

        return (
            root.getAttribute(
                "data-theme"
            )
            ||
            "light"
        );

    }


    function refreshThemeButtons() {

        const currentTheme =
            getCurrentTheme();


        themeButtons.forEach(
            (button) => {

                const buttonTheme =
                    button.dataset.themeChoice;


                const isActive =
                    buttonTheme
                    ===
                    currentTheme;


                button.classList.toggle(
                    "is-active",
                    isActive
                );


                button.setAttribute(
                    "aria-pressed",
                    isActive
                        ? "true"
                        : "false"
                );

            }
        );

    }


    function applyTheme(
        theme
    ) {

        if (
            theme !== "light"
            &&
            theme !== "dark"
        ) {

            return;

        }


        root.setAttribute(
            "data-theme",
            theme
        );


        localStorage.setItem(
            "bika-theme",
            theme
        );


        refreshThemeButtons();

    }


    themeButtons.forEach(
        (button) => {

            button.addEventListener(
                "click",
                () => {

                    applyTheme(
                        button.dataset.themeChoice
                    );

                }
            );

        }
    );


    refreshThemeButtons();



    /* =====================================================
       LOGOUT CONFIRMATION
       ===================================================== */

    const openLogoutButton =
        document.getElementById(
            "openLogoutModal"
        );


    const logoutBackdrop =
        document.getElementById(
            "logoutConfirmBackdrop"
        );


    const cancelLogoutButton =
        document.getElementById(
            "cancelLogoutButton"
        );


    /*
     * Do nothing on pages without the authenticated shell.
     */

    if (
        !openLogoutButton
        ||
        !logoutBackdrop
        ||
        !cancelLogoutButton
    ) {

        return;

    }



    let closeTimer =
        null;


    /* =====================================================
       OPEN
       ===================================================== */

    function openLogoutModal() {

        if (
            closeTimer
        ) {

            window.clearTimeout(
                closeTimer
            );

            closeTimer =
                null;

        }


        logoutBackdrop.hidden =
            false;


        document.documentElement.classList.add(
            "logout-modal-open"
        );


        /*
         * Wait one frame so opacity / transform
         * transition can animate.
         */

        window.requestAnimationFrame(
            () => {

                logoutBackdrop.classList.add(
                    "is-open"
                );

            }
        );


        window.setTimeout(
            () => {

                cancelLogoutButton.focus();

            },
            50
        );

    }



    /* =====================================================
       CLOSE
       ===================================================== */

    function closeLogoutModal() {

        logoutBackdrop.classList.remove(
            "is-open"
        );


        document.documentElement.classList.remove(
            "logout-modal-open"
        );


        closeTimer =
            window.setTimeout(
                () => {

                    logoutBackdrop.hidden =
                        true;


                    openLogoutButton.focus();


                    closeTimer =
                        null;

                },
                180
            );

    }



    /* =====================================================
       OPEN BUTTON
       ===================================================== */

    openLogoutButton.addEventListener(
        "click",
        (event) => {

            event.preventDefault();

            openLogoutModal();

        }
    );



    /* =====================================================
       CANCEL BUTTON
       ===================================================== */

    cancelLogoutButton.addEventListener(
        "click",
        (event) => {

            event.preventDefault();

            closeLogoutModal();

        }
    );



    /* =====================================================
       CLICK BACKDROP TO CLOSE
       ===================================================== */

    logoutBackdrop.addEventListener(
        "click",
        (event) => {

            if (
                event.target
                ===
                logoutBackdrop
            ) {

                closeLogoutModal();

            }

        }
    );



    /* =====================================================
       ESC TO CLOSE
       ===================================================== */

    document.addEventListener(
        "keydown",
        (event) => {

            if (
                event.key
                ===
                "Escape"
                &&
                !logoutBackdrop.hidden
            ) {

                closeLogoutModal();

            }

        }
    );

})();