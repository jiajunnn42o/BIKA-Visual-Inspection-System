/* =========================================================
   BIKA ACCOUNT PAGE
   ========================================================= */

(() => {

    "use strict";


    const page =
        document.querySelector(
            "[data-account-page]"
        );


    if (!page) {
        return;
    }



    /* =====================================================
       PERSONAL INFORMATION
       ===================================================== */

    const personalForm =
        page.querySelector(
            "[data-personal-form]"
        )
        ||
        page.querySelector(
            'form[action*="personal-information"]'
        );


    const usernameInput =
        page.querySelector(
            "[data-username-input]"
        )
        ||
        page.querySelector(
            'input[name="username"]'
        );


    const usernameStatus =
        page.querySelector(
            "[data-username-status]"
        );


    const personalSaveButton =
        page.querySelector(
            "[data-personal-save-button]"
        );


    let usernameCheckTimer =
        null;


    let usernameCheckController =
        null;



    /* =====================================================
       USERNAME STATE
       ===================================================== */

    function setUsernameState(
        state,
        message = ""
    ) {

        if (usernameInput) {

            usernameInput.classList.remove(
                "is-username-checking",
                "is-username-available",
                "is-username-unavailable"
            );


            if (
                state === "checking"
            ) {

                usernameInput.classList.add(
                    "is-username-checking"
                );

            }


            else if (
                state === "available"
            ) {

                usernameInput.classList.add(
                    "is-username-available"
                );

            }


            else if (
                state === "unavailable"
            ) {

                usernameInput.classList.add(
                    "is-username-unavailable"
                );

            }

        }



        if (usernameStatus) {

            usernameStatus.classList.remove(
                "is-checking",
                "is-available",
                "is-unavailable"
            );


            if (
                state === "checking"
            ) {

                usernameStatus.classList.add(
                    "is-checking"
                );

            }


            else if (
                state === "available"
            ) {

                usernameStatus.classList.add(
                    "is-available"
                );

            }


            else if (
                state === "unavailable"
            ) {

                usernameStatus.classList.add(
                    "is-unavailable"
                );

            }


            usernameStatus.textContent =
                message;

        }



        if (personalSaveButton) {

            const blocked =
                (
                    state === "checking"
                    ||
                    state === "unavailable"
                );


            personalSaveButton.disabled =
                blocked;


            if (
                state === "checking"
            ) {

                personalSaveButton.title =
                    "Checking username availability.";

            }


            else if (
                state === "unavailable"
            ) {

                personalSaveButton.title =
                    "Choose an available username before saving.";

            }


            else {

                personalSaveButton.title =
                    "";

            }

        }

    }



    /* =====================================================
       CHECK USERNAME
       ===================================================== */

    async function checkUsernameAvailability() {

        if (!usernameInput) {
            return true;
        }


        const username =
            String(
                usernameInput.value
                ||
                ""
            ).trim();


        const endpoint =
            usernameInput.dataset
                .usernameCheckUrl
            ||
            "/account/check-username";


        if (!username) {

            setUsernameState(
                "unavailable",
                "Required"
            );


            return false;

        }


        if (
            username.length < 3
        ) {

            setUsernameState(
                "unavailable",
                "At least 3 characters"
            );


            return false;

        }


        if (
            usernameCheckController
        ) {

            usernameCheckController.abort();

        }


        usernameCheckController =
            new AbortController();


        const checkedValue =
            username;


        setUsernameState(
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
                "username",
                username
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
                            usernameCheckController.signal

                    }
                );


            if (!response.ok) {

                throw new Error(
                    `Username check failed (${response.status})`
                );

            }


            const data =
                await response.json();


            if (
                String(
                    usernameInput.value
                    ||
                    ""
                ).trim()
                !==
                checkedValue
            ) {

                return false;

            }


            if (
                data.available === true
            ) {

                setUsernameState(
                    "available",
                    data.message
                    ||
                    "Available"
                );


                return true;

            }


            setUsernameState(
                "unavailable",
                data.message
                ||
                "Already in use"
            );


            return false;

        }

        catch (error) {

            if (
                error.name
                ===
                "AbortError"
            ) {

                return false;

            }


            console.error(
                "[BIKA] Username check failed:",
                error
            );


            setUsernameState(
                "unavailable",
                "Unable to verify"
            );


            return false;

        }

    }



    function queueUsernameCheck() {

        if (!usernameInput) {
            return;
        }


        if (
            usernameCheckTimer
        ) {

            window.clearTimeout(
                usernameCheckTimer
            );

        }


        setUsernameState(
            "checking",
            "Checking..."
        );


        usernameCheckTimer =
            window.setTimeout(
                checkUsernameAvailability,
                350
            );

    }



    if (usernameInput) {

        usernameInput.addEventListener(
            "input",
            queueUsernameCheck
        );


        usernameInput.addEventListener(
            "blur",
            () => {

                if (
                    usernameCheckTimer
                ) {

                    window.clearTimeout(
                        usernameCheckTimer
                    );

                }


                checkUsernameAvailability();

            }
        );


        checkUsernameAvailability();

    }



    if (personalForm) {

        personalForm.addEventListener(
            "submit",
            async (event) => {

                event.preventDefault();


                if (
                    usernameCheckTimer
                ) {

                    window.clearTimeout(
                        usernameCheckTimer
                    );

                }


                const available =
                    await checkUsernameAvailability();


                if (!available) {
                    return;
                }


                HTMLFormElement
                    .prototype
                    .submit
                    .call(
                        personalForm
                    );

            }
        );

    }



    /* =====================================================
       PROFILE PHOTO
       ===================================================== */

    const photoInput =
        page.querySelector(
            "[data-profile-photo-input]"
        );


    if (photoInput) {

        photoInput.addEventListener(
            "change",
            () => {

                if (
                    !photoInput.files
                    ||
                    photoInput.files.length === 0
                ) {

                    return;

                }


                const form =
                    photoInput.closest(
                        "form"
                    );


                if (form) {

                    HTMLFormElement
                        .prototype
                        .submit
                        .call(
                            form
                        );

                }

            }
        );

    }



    /* =====================================================
       PASSWORD SHOW / HIDE
       ===================================================== */

    const passwordToggleButtons =
        Array.from(
            page.querySelectorAll(
                "[data-password-toggle]"
            )
        );


    const passwordFieldMap = {

        current:
            "current_password",

        new:
            "new_password",

        confirm:
            "confirm_password"

    };


    passwordToggleButtons.forEach(
        (button) => {

            const key =
                button.dataset.passwordToggle;


            const input =
                page.querySelector(
                    `[data-password-input="${key}"]`
                )
                ||
                page.querySelector(
                    `input[name="${passwordFieldMap[key]}"]`
                );


            if (!input) {
                return;
            }


            button.addEventListener(
                "click",
                (event) => {

                    event.preventDefault();


                    const hidden =
                        input.type === "password";


                    input.type =
                        hidden
                            ? "text"
                            : "password";


                    button.classList.toggle(
                        "is-visible",
                        hidden
                    );


                    button.setAttribute(
                        "aria-pressed",
                        hidden
                            ? "true"
                            : "false"
                    );


                    button.setAttribute(
                        "aria-label",
                        hidden
                            ? "Hide password"
                            : "Show password"
                    );


                    input.focus();

                }
            );

        }
    );



    /* =====================================================
       BEAUTIFUL WORK SELECTS
       ===================================================== */

    function closeWorkSelect(
        wrapper
    ) {

        if (!wrapper) {
            return;
        }


        const menu =
            wrapper.querySelector(
                "[data-work-select-menu]"
            );


        const trigger =
            wrapper.querySelector(
                "[data-work-select-trigger]"
            );


        wrapper.classList.remove(
            "is-open"
        );


        if (menu) {

            menu.hidden =
                true;

        }


        if (trigger) {

            trigger.setAttribute(
                "aria-expanded",
                "false"
            );

        }

    }



    function closeAllWorkSelects(
        except = null
    ) {

        page
            .querySelectorAll(
                "[data-work-select]"
            )
            .forEach(
                (wrapper) => {

                    if (
                        wrapper === except
                    ) {
                        return;
                    }


                    closeWorkSelect(
                        wrapper
                    );

                }
            );

    }



    const workSelects =
        Array.from(
            page.querySelectorAll(
                "[data-work-select]"
            )
        );


    workSelects.forEach(
        (wrapper) => {

            const nativeSelect =
                wrapper.querySelector(
                    "[data-work-native-select]"
                );


            const trigger =
                wrapper.querySelector(
                    "[data-work-select-trigger]"
                );


            const label =
                wrapper.querySelector(
                    "[data-work-select-label]"
                );


            const menu =
                wrapper.querySelector(
                    "[data-work-select-menu]"
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



            function syncLabel() {

                const selected =
                    nativeSelect
                        .selectedOptions[0];


                if (!selected) {
                    return;
                }


                label.textContent =
                    selected.textContent.trim();

            }



            function buildOptions() {

                menu.innerHTML =
                    "";


                Array.from(
                    nativeSelect.options
                )
                .forEach(
                    (option) => {

                        const button =
                            document.createElement(
                                "button"
                            );


                        button.type =
                            "button";


                        button.className =
                            "account-work-select-option";


                        if (
                            option.selected
                        ) {

                            button.classList.add(
                                "is-selected"
                            );

                        }


                        const text =
                            document.createElement(
                                "span"
                            );


                        text.textContent =
                            option.textContent.trim();


                        const check =
                            document.createElement(
                                "span"
                            );


                        check.className =
                            "account-work-option-check";


                        check.textContent =
                            "✓";


                        button.append(
                            text,
                            check
                        );


                        button.addEventListener(
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
                                            bubbles:
                                                true
                                        }
                                    )
                                );


                                syncLabel();


                                menu
                                    .querySelectorAll(
                                        ".account-work-select-option"
                                    )
                                    .forEach(
                                        (item) => {

                                            item.classList.remove(
                                                "is-selected"
                                            );

                                        }
                                    );


                                button.classList.add(
                                    "is-selected"
                                );


                                closeWorkSelect(
                                    wrapper
                                );

                            }
                        );


                        menu.appendChild(
                            button
                        );

                    }
                );

            }



            buildOptions();

            syncLabel();



            trigger.addEventListener(
                "click",
                (event) => {

                    event.preventDefault();

                    event.stopPropagation();


                    const isOpen =
                        wrapper.classList.contains(
                            "is-open"
                        );


                    closeAllWorkSelects(
                        wrapper
                    );


                    if (isOpen) {

                        closeWorkSelect(
                            wrapper
                        );

                        return;

                    }


                    menu.hidden =
                        false;


                    wrapper.classList.add(
                        "is-open"
                    );


                    trigger.setAttribute(
                        "aria-expanded",
                        "true"
                    );

                }
            );

        }
    );



    /* =====================================================
       EMPLOYEE ID UNIQUE
       ===================================================== */

    const workForm =
        page.querySelector(
            "[data-work-form]"
        );


    const workSaveButton =
        page.querySelector(
            "[data-work-save-button]"
        );


    const employeeIdInput =
        page.querySelector(
            "[data-employee-id-input]"
        );


    const employeeIdStatus =
        page.querySelector(
            "[data-employee-id-status]"
        );


    let employeeCheckTimer =
        null;


    let employeeCheckController =
        null;


    let employeeIdState =
        "idle";



    function setEmployeeIdState(
        state,
        message = ""
    ) {

        employeeIdState =
            state;


        if (employeeIdInput) {

            employeeIdInput.classList.remove(
                "is-employee-checking",
                "is-employee-available",
                "is-employee-unavailable"
            );


            if (
                state === "checking"
            ) {

                employeeIdInput.classList.add(
                    "is-employee-checking"
                );

            }


            else if (
                state === "available"
            ) {

                employeeIdInput.classList.add(
                    "is-employee-available"
                );

            }


            else if (
                state === "unavailable"
            ) {

                employeeIdInput.classList.add(
                    "is-employee-unavailable"
                );

            }

        }



        if (employeeIdStatus) {

            employeeIdStatus.classList.remove(
                "is-checking",
                "is-available",
                "is-unavailable"
            );


            if (
                state === "checking"
            ) {

                employeeIdStatus.classList.add(
                    "is-checking"
                );

            }


            else if (
                state === "available"
            ) {

                employeeIdStatus.classList.add(
                    "is-available"
                );

            }


            else if (
                state === "unavailable"
            ) {

                employeeIdStatus.classList.add(
                    "is-unavailable"
                );

            }


            employeeIdStatus.textContent =
                message;

        }



        if (workSaveButton) {

            const blocked =
                (
                    state === "checking"
                    ||
                    state === "unavailable"
                );


            workSaveButton.disabled =
                blocked;


            if (
                state === "checking"
            ) {

                workSaveButton.title =
                    "Checking Employee ID availability.";

            }


            else if (
                state === "unavailable"
            ) {

                workSaveButton.title =
                    "Choose an available Employee ID before saving.";

            }


            else {

                workSaveButton.title =
                    "";

            }

        }

    }



    async function checkEmployeeId() {

        if (!employeeIdInput) {
            return true;
        }


        const employeeId =
            String(
                employeeIdInput.value
                ||
                ""
            )
            .trim()
            .toUpperCase();


        const endpoint =
            employeeIdInput.dataset
                .employeeIdCheckUrl;


        if (!employeeId) {

            setEmployeeIdState(
                "unavailable",
                "Required"
            );


            return false;

        }


        if (!endpoint) {

            setEmployeeIdState(
                "unavailable",
                "Unable to verify"
            );


            return false;

        }


        if (
            employeeCheckController
        ) {

            employeeCheckController.abort();

        }


        employeeCheckController =
            new AbortController();


        const checkedValue =
            employeeId;


        setEmployeeIdState(
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
                "employee_id",
                employeeId
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
                            employeeCheckController.signal

                    }
                );


            if (!response.ok) {

                throw new Error(
                    `Employee ID check failed (${response.status})`
                );

            }


            const data =
                await response.json();


            if (
                String(
                    employeeIdInput.value
                    ||
                    ""
                )
                .trim()
                .toUpperCase()
                !==
                checkedValue
            ) {

                return false;

            }


            if (
                data.available === true
            ) {

                setEmployeeIdState(
                    "available",
                    data.message
                    ||
                    "Available"
                );


                return true;

            }


            setEmployeeIdState(
                "unavailable",
                data.message
                ||
                "Already in use"
            );


            return false;

        }

        catch (error) {

            if (
                error.name
                ===
                "AbortError"
            ) {

                return false;

            }


            console.error(
                "[BIKA] Employee ID check failed:",
                error
            );


            setEmployeeIdState(
                "unavailable",
                "Unable to verify"
            );


            return false;

        }

    }



    function queueEmployeeIdCheck() {

        if (!employeeIdInput) {
            return;
        }


        if (
            employeeCheckTimer
        ) {

            window.clearTimeout(
                employeeCheckTimer
            );

        }


        setEmployeeIdState(
            "checking",
            "Checking..."
        );


        employeeCheckTimer =
            window.setTimeout(
                checkEmployeeId,
                350
            );

    }



    if (employeeIdInput) {

        employeeIdInput.addEventListener(
            "input",
            () => {

                employeeIdInput.value =
                    employeeIdInput.value
                        .toUpperCase();


                queueEmployeeIdCheck();

            }
        );


        employeeIdInput.addEventListener(
            "blur",
            () => {

                if (
                    employeeCheckTimer
                ) {

                    window.clearTimeout(
                        employeeCheckTimer
                    );

                }


                checkEmployeeId();

            }
        );


        checkEmployeeId();

    }



    /* =====================================================
       WORK SAVE CONFIRMATION
       ===================================================== */

    function showWorkConfirmation(
        form
    ) {

        let backdrop =
            document.querySelector(
                "[data-work-confirm]"
            );


        if (!backdrop) {

            backdrop =
                document.createElement(
                    "div"
                );


            backdrop.className =
                "account-confirm-backdrop";


            backdrop.setAttribute(
                "data-work-confirm",
                ""
            );


            document.body.appendChild(
                backdrop
            );

        }


        backdrop.innerHTML = `

            <div
                class="account-confirm-dialog"
                role="dialog"
                aria-modal="true"
            >

                <div class="account-confirm-icon">
                    ✓
                </div>

                <h3>
                    Save work information?
                </h3>

                <p>
                    Your work information will be updated with the new values.
                </p>

                <div class="account-confirm-actions">

                    <button
                        type="button"
                        class="account-confirm-cancel"
                        data-work-confirm-cancel
                    >
                        Cancel
                    </button>

                    <button
                        type="button"
                        class="account-confirm-submit"
                        data-work-confirm-submit
                    >
                        Save Changes
                    </button>

                </div>

            </div>

        `;


        const cancel =
            backdrop.querySelector(
                "[data-work-confirm-cancel]"
            );


        const submit =
            backdrop.querySelector(
                "[data-work-confirm-submit]"
            );


        function closeConfirmation() {

            backdrop.remove();

        }


        cancel.addEventListener(
            "click",
            closeConfirmation
        );


        submit.addEventListener(
            "click",
            () => {

                submit.disabled =
                    true;


                HTMLFormElement
                    .prototype
                    .submit
                    .call(
                        form
                    );

            }
        );

    }



    if (workForm) {

        workForm.addEventListener(
            "submit",
            async (event) => {

                event.preventDefault();


                if (
                    employeeCheckTimer
                ) {

                    window.clearTimeout(
                        employeeCheckTimer
                    );

                }


                const available =
                    await checkEmployeeId();


                if (!available) {
                    return;
                }


                showWorkConfirmation(
                    workForm
                );

            }
        );

    }



    /* =====================================================
       NOTIFICATION
       ===================================================== */

    const notificationToggles =
        Array.from(
            page.querySelectorAll(
                "[data-account-toggle]"
            )
        );


    notificationToggles.forEach(
        (toggle) => {

            const name =
                toggle.dataset.accountToggle;


            const key =
                `bika-account-notification-${name}`;


            const stored =
                localStorage.getItem(
                    key
                );


            if (
                stored === "true"
                ||
                stored === "false"
            ) {

                toggle.checked =
                    stored === "true";

            }


            toggle.addEventListener(
                "change",
                () => {

                    localStorage.setItem(
                        key,
                        String(
                            toggle.checked
                        )
                    );

                }
            );

        }
    );



    /* =====================================================
       SAVE SUCCESS TOAST
       ===================================================== */

    function showSaveToast(
        title,
        message
    ) {

        const previous =
            document.querySelector(
                "[data-account-save-toast]"
            );


        if (previous) {

            previous.remove();

        }


        const toast =
            document.createElement(
                "div"
            );


        toast.className =
            "account-save-toast";


        toast.setAttribute(
            "data-account-save-toast",
            ""
        );


        toast.innerHTML = `

            <iconsax-icon
                name="tick-circle"
                type="bold"
                size="21"
                color="currentColor"
            ></iconsax-icon>

            <div>

                <strong>
                    ${title}
                </strong>

                <span>
                    ${message}
                </span>

            </div>

        `;


        document.body.appendChild(
            toast
        );


        requestAnimationFrame(
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



    const url =
        new URL(
            window.location.href
        );


    const saved =
        url.searchParams.get(
            "saved"
        );


    if (
        saved === "work"
    ) {

        const flashes =
            Array.from(
                page.querySelectorAll(
                    ".account-flash-success"
                )
            );


        flashes.forEach(
            (flash) => {

                if (
                    String(
                        flash.textContent
                    )
                    .toLowerCase()
                    .includes(
                        "work information"
                    )
                ) {

                    flash.remove();

                }

            }
        );


        showSaveToast(
            "Saved successfully",
            "Work information has been updated."
        );


        url.searchParams.delete(
            "saved"
        );


        window.history.replaceState(
            {},
            "",
            url.toString()
        );

    }



    /* =====================================================
       CLOSE DROPDOWN ON OUTSIDE CLICK
       ===================================================== */

    document.addEventListener(
        "click",
        (event) => {

            const inside =
                event.target.closest(
                    "[data-work-select]"
                );


            if (!inside) {

                closeAllWorkSelects();

            }

        }
    );



    /* =====================================================
       AUTO-HIDE FLASH
       ===================================================== */

    const flashMessages =
        Array.from(
            page.querySelectorAll(
                "[data-account-flash]"
            )
        );


    if (
        flashMessages.length
    ) {

        window.setTimeout(
            () => {

                flashMessages.forEach(
                    (flash) => {

                        flash.style.opacity =
                            "0";


                        flash.style.transform =
                            "translateY(-4px)";

                    }
                );


                window.setTimeout(
                    () => {

                        const stack =
                            page.querySelector(
                                "[data-account-flash-stack]"
                            );


                        if (
                            stack
                            &&
                            !stack.children.length
                        ) {

                            stack.remove();

                        }

                    },
                    220
                );

            },
            2600
        );

    }


})();