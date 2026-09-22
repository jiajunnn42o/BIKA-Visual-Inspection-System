(() => {

    "use strict";


    const page =
        document.querySelector(
            "[data-account-page]"
        );


    if (!page) {
        return;
    }


    const form =
        page.querySelector(
            "[data-work-information-form]"
        );


    if (!form) {
        return;
    }


    const employeeInput =
        form.querySelector(
            "[data-employee-id-input]"
        );


    const statusText =
        form.querySelector(
            "[data-employee-id-status]"
        );


    const saveButton =
        form.querySelector(
            "[data-work-save-button]"
        );


    if (
        !employeeInput
        ||
        !saveButton
    ) {
        return;
    }


    let timer =
        null;


    let controller =
        null;


    let employeeState =
        "idle";


    /* =====================================================
       STATE
       ===================================================== */

    function setState(
        state,
        message = ""
    ) {

        employeeState =
            state;


        employeeInput.classList.remove(
            "is-employee-checking",
            "is-employee-available",
            "is-employee-unavailable"
        );


        if (
            state === "checking"
        ) {

            employeeInput.classList.add(
                "is-employee-checking"
            );

        }


        else if (
            state === "available"
        ) {

            employeeInput.classList.add(
                "is-employee-available"
            );

        }


        else if (
            state === "unavailable"
        ) {

            employeeInput.classList.add(
                "is-employee-unavailable"
            );

        }


        if (statusText) {

            statusText.classList.remove(
                "is-checking",
                "is-available",
                "is-unavailable"
            );


            if (
                state === "checking"
            ) {

                statusText.classList.add(
                    "is-checking"
                );

            }


            else if (
                state === "available"
            ) {

                statusText.classList.add(
                    "is-available"
                );

            }


            else if (
                state === "unavailable"
            ) {

                statusText.classList.add(
                    "is-unavailable"
                );

            }


            statusText.textContent =
                message;

        }


        saveButton.disabled =
            (
                state === "checking"
                ||
                state === "unavailable"
            );

    }


    /* =====================================================
       CHECK
       ===================================================== */

    async function checkEmployeeId() {

        const value =
            String(
                employeeInput.value
                ||
                ""
            )
            .trim()
            .toUpperCase();


        employeeInput.value =
            value;


        if (!value) {

            setState(
                "unavailable",
                "Required"
            );

            return false;

        }


        const endpoint =
            employeeInput.dataset.checkUrl;


        if (!endpoint) {

            setState(
                "unavailable",
                "Unable to verify"
            );

            return false;

        }


        if (controller) {
            controller.abort();
        }


        controller =
            new AbortController();


        const checkedValue =
            value;


        setState(
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
                    `HTTP ${response.status}`
                );

            }


            const data =
                await response.json();


            const currentValue =
                String(
                    employeeInput.value
                    ||
                    ""
                )
                .trim()
                .toUpperCase();


            if (
                currentValue
                !==
                checkedValue
            ) {

                return false;

            }


            if (
                data.available
                ===
                true
            ) {

                setState(
                    "available",
                    data.message
                    ||
                    "Available"
                );

                return true;

            }


            setState(
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


            setState(
                "unavailable",
                "Unable to verify"
            );


            return false;

        }

    }


    /* =====================================================
       INPUT
       ===================================================== */

    employeeInput.addEventListener(
        "input",
        () => {

            employeeInput.value =
                employeeInput.value
                    .toUpperCase();


            if (timer) {

                window.clearTimeout(
                    timer
                );

            }


            setState(
                "checking",
                "Checking..."
            );


            timer =
                window.setTimeout(
                    checkEmployeeId,
                    350
                );

        }
    );


    employeeInput.addEventListener(
        "blur",
        () => {

            if (timer) {

                window.clearTimeout(
                    timer
                );

            }


            checkEmployeeId();

        }
    );


    /* =====================================================
       FINAL CHECK BEFORE SUBMIT
       ===================================================== */

    form.addEventListener(
        "submit",
        async (event) => {

            event.preventDefault();


            if (timer) {

                window.clearTimeout(
                    timer
                );

            }


            const valid =
                await checkEmployeeId();


            if (!valid) {
                return;
            }


            saveButton.disabled =
                true;


            saveButton.textContent =
                "Submitting...";


            HTMLFormElement
                .prototype
                .submit
                .call(
                    form
                );

        }
    );


    /* =====================================================
       INITIAL
       ===================================================== */

    checkEmployeeId();


})();