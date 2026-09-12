document.addEventListener(
    "DOMContentLoaded",
    () => {

        /* =================================================
           PASSWORD SHOW / HIDE
           ================================================= */

        const passwordButtons =
            document.querySelectorAll(
                "[data-password-toggle]"
            );


        passwordButtons.forEach(
            (button) => {

                const inputId =
                    button.getAttribute(
                        "data-password-toggle"
                    );

                const input =
                    document.getElementById(
                        inputId
                    );


                if (!input) {
                    return;
                }


                button.addEventListener(
                    "click",
                    () => {

                        const willShowPassword =
                            input.type === "password";


                        input.type =
                            willShowPassword
                                ? "text"
                                : "password";


                        button.classList.toggle(
                            "is-visible",
                            willShowPassword
                        );


                        button.setAttribute(
                            "aria-pressed",
                            String(
                                willShowPassword
                            )
                        );


                        button.setAttribute(
                            "aria-label",
                            willShowPassword
                                ? "Hide password"
                                : "Show password"
                        );

                    }
                );

            }
        );


        /* =================================================
           OTP COMPONENT
           ================================================= */

        const otpGroups =
            document.querySelectorAll(
                "[data-otp-group]"
            );


        otpGroups.forEach(
            (group) => {

                const boxes =
                    Array.from(
                        group.querySelectorAll(
                            "[data-otp-box]"
                        )
                    );


                const hiddenInput =
                    group.querySelector(
                        "[data-otp-hidden]"
                    );


                if (
                    boxes.length !== 6
                    ||
                    !hiddenInput
                ) {
                    return;
                }


                /* -----------------------------------------
                   Synchronize the six UI boxes into the
                   actual WTForms hidden field.
                   ----------------------------------------- */

                const syncHiddenValue = () => {

                    const value =
                        boxes
                            .map(
                                (box) =>
                                    box.value
                            )
                            .join("")
                            .replace(/\D/g, "")
                            .slice(0, 6);


                    hiddenInput.value =
                        value;


                    boxes.forEach(
                        (box) => {

                            box.classList.toggle(
                                "has-value",
                                box.value !== ""
                            );

                        }
                    );

                };


                /* -----------------------------------------
                   Restore server-returned value.

                   Useful if validation fails and Flask
                   redisplays the submitted code.
                   ----------------------------------------- */

                const initialValue =
                    (
                        hiddenInput.value
                        || ""
                    )
                        .replace(/\D/g, "")
                        .slice(0, 6);


                if (initialValue) {

                    initialValue
                        .split("")
                        .forEach(
                            (
                                digit,
                                index
                            ) => {

                                if (boxes[index]) {
                                    boxes[index].value =
                                        digit;
                                }

                            }
                        );

                    syncHiddenValue();

                }


                /* -----------------------------------------
                   Input
                   ----------------------------------------- */

                boxes.forEach(
                    (
                        box,
                        index
                    ) => {

                        box.addEventListener(
                            "input",
                            () => {

                                const cleanValue =
                                    box.value
                                        .replace(/\D/g, "");


                                /*
                                 * Mobile OTP autofill may put
                                 * the entire six-digit code
                                 * into the first field.
                                 */

                                if (
                                    cleanValue.length
                                    > 1
                                ) {

                                    const digits =
                                        cleanValue
                                            .slice(0, 6)
                                            .split("");


                                    digits.forEach(
                                        (
                                            digit,
                                            digitIndex
                                        ) => {

                                            if (
                                                boxes[
                                                    digitIndex
                                                ]
                                            ) {

                                                boxes[
                                                    digitIndex
                                                ].value =
                                                    digit;

                                            }

                                        }
                                    );


                                    syncHiddenValue();


                                    const finalIndex =
                                        Math.min(
                                            digits.length,
                                            6
                                        )
                                        - 1;


                                    boxes[
                                        finalIndex
                                    ]?.focus();


                                    return;

                                }


                                box.value =
                                    cleanValue
                                        .slice(0, 1);


                                syncHiddenValue();


                                if (
                                    box.value
                                    &&
                                    index
                                    < boxes.length - 1
                                ) {

                                    boxes[
                                        index + 1
                                    ].focus();

                                }

                            }
                        );


                        /* ---------------------------------
                           Keyboard navigation
                           --------------------------------- */

                        box.addEventListener(
                            "keydown",
                            (event) => {

                                if (
                                    event.key
                                    === "Backspace"
                                ) {

                                    /*
                                     * Empty current box:
                                     * move back and delete.
                                     */

                                    if (
                                        !box.value
                                        &&
                                        index > 0
                                    ) {

                                        event.preventDefault();

                                        boxes[
                                            index - 1
                                        ].value = "";

                                        boxes[
                                            index - 1
                                        ].focus();

                                        syncHiddenValue();

                                    }

                                    return;

                                }


                                if (
                                    event.key
                                    === "ArrowLeft"
                                    &&
                                    index > 0
                                ) {

                                    event.preventDefault();

                                    boxes[
                                        index - 1
                                    ].focus();

                                    return;

                                }


                                if (
                                    event.key
                                    === "ArrowRight"
                                    &&
                                    index
                                    < boxes.length - 1
                                ) {

                                    event.preventDefault();

                                    boxes[
                                        index + 1
                                    ].focus();

                                }

                            }
                        );


                        /* ---------------------------------
                           Select digit when focused.
                           --------------------------------- */

                        box.addEventListener(
                            "focus",
                            () => {

                                box.select();

                            }
                        );

                    }
                );


                /* -----------------------------------------
                   Paste complete OTP
                   ----------------------------------------- */

                group.addEventListener(
                    "paste",
                    (event) => {

                        const pastedText =
                            event.clipboardData
                                ?.getData("text")
                            || "";


                        const digits =
                            pastedText
                                .replace(/\D/g, "")
                                .slice(0, 6);


                        if (!digits) {
                            return;
                        }


                        event.preventDefault();


                        boxes.forEach(
                            (box) => {
                                box.value = "";
                            }
                        );


                        digits
                            .split("")
                            .forEach(
                                (
                                    digit,
                                    index
                                ) => {

                                    if (boxes[index]) {

                                        boxes[
                                            index
                                        ].value =
                                            digit;

                                    }

                                }
                            );


                        syncHiddenValue();


                        const focusIndex =
                            Math.min(
                                digits.length,
                                6
                            )
                            - 1;


                        boxes[
                            focusIndex
                        ]?.focus();

                    }
                );


                /* -----------------------------------------
                   Always synchronize immediately before
                   the surrounding form is submitted.
                   ----------------------------------------- */

                const parentForm =
                    group.closest(
                        "form"
                    );


                if (parentForm) {

                    parentForm.addEventListener(
                        "submit",
                        () => {

                            syncHiddenValue();

                        }
                    );

                }

            }
        );


        /* =================================================
           RESEND COUNTDOWN
           ================================================= */

        const resendForms =
            document.querySelectorAll(
                "[data-resend-form]"
            );


        resendForms.forEach(
            (form) => {

                const button =
                    form.querySelector(
                        ".otp-resend-button"
                    );


                if (!button) {
                    return;
                }


                const cooldownSeconds =
                    Number(
                        form.dataset
                            .resendCooldown
                    )
                    || 60;


                /*
                 * Use the current URL as part of the
                 * storage key so Email Verify and
                 * Password Reset do not share timers.
                 */

                const storageKey =
                    (
                        "bika-resend-end:"
                        + window.location.pathname
                    );


                const now =
                    Date.now();


                let endTime =
                    Number(
                        sessionStorage.getItem(
                            storageKey
                        )
                    );


                /*
                 * If there is no active local timer,
                 * start a fresh countdown.
                 */

                if (
                    !endTime
                    ||
                    endTime <= now
                ) {

                    endTime =
                        now
                        +
                        (
                            cooldownSeconds
                            * 1000
                        );


                    sessionStorage.setItem(
                        storageKey,
                        String(endTime)
                    );

                }


                const originalLabel =
                    button.value
                    || "Resend Code";


                const updateCountdown = () => {

                    const remainingMilliseconds =
                        endTime
                        - Date.now();


                    const remainingSeconds =
                        Math.max(
                            0,
                            Math.ceil(
                                remainingMilliseconds
                                / 1000
                            )
                        );


                    if (
                        remainingSeconds > 0
                    ) {

                        button.disabled =
                            true;

                        button.value =
                            `Resend in ${remainingSeconds}s`;

                        return true;

                    }


                    button.disabled =
                        false;

                    button.value =
                        originalLabel;


                    sessionStorage.removeItem(
                        storageKey
                    );


                    return false;

                };


                updateCountdown();


                const countdownTimer =
                    window.setInterval(
                        () => {

                            const active =
                                updateCountdown();


                            if (!active) {

                                window.clearInterval(
                                    countdownTimer
                                );

                            }

                        },
                        250
                    );


                /*
                 * When the resend form actually
                 * submits, prepare a new local timer
                 * for the next page load.
                 */

                form.addEventListener(
                    "submit",
                    () => {

                        const nextEndTime =
                            Date.now()
                            +
                            (
                                cooldownSeconds
                                * 1000
                            );


                        sessionStorage.setItem(
                            storageKey,
                            String(
                                nextEndTime
                            )
                        );

                    }
                );

            }
        );

    }
);