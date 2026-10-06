/* =========================================================
   BIKA ACCOUNT CONTACT CHANGE
   Email / Phone OTP verification modal
   ========================================================= */

(() => {

    "use strict";


    const page =
        document.querySelector(
            "[data-account-page]"
        );

    const modal =
        document.querySelector(
            "[data-contact-modal]"
        );


    if (
        !page
        ||
        !modal
    ) {
        return;
    }


    const openButtons =
        Array.from(
            page.querySelectorAll(
                "[data-contact-change]"
            )
        );


    const closeButtons =
        Array.from(
            modal.querySelectorAll(
                "[data-contact-close]"
            )
        );


    const title =
        modal.querySelector(
            "[data-contact-title]"
        );

    const subtitle =
        modal.querySelector(
            "[data-contact-subtitle]"
        );

    const currentLabel =
        modal.querySelector(
            "[data-contact-current-label]"
        );

    const currentValue =
        modal.querySelector(
            "[data-contact-current-value]"
        );

    const newLabel =
        modal.querySelector(
            "[data-contact-new-label]"
        );

    const valueInput =
        modal.querySelector(
            "[data-contact-value]"
        );

    const codeInput =
        modal.querySelector(
            "[data-contact-code]"
        );

    const codeMessage =
        modal.querySelector(
            "[data-contact-code-message]"
        );

    const entryStep =
        modal.querySelector(
            '[data-contact-step="entry"]'
        );

    const verifyStep =
        modal.querySelector(
            '[data-contact-step="verify"]'
        );

    const entryError =
        modal.querySelector(
            "[data-contact-entry-error]"
        );

    const verifyError =
        modal.querySelector(
            "[data-contact-verify-error]"
        );

    const sendButton =
        modal.querySelector(
            "[data-contact-send]"
        );

    const verifyButton =
        modal.querySelector(
            "[data-contact-verify]"
        );

    const resendButton =
        modal.querySelector(
            "[data-contact-resend]"
        );

    const countdown =
        modal.querySelector(
            "[data-contact-countdown]"
        );

    const valueShell =
        modal.querySelector(
            "[data-contact-value-shell]"
        );


    const phonePrefix =
        modal.querySelector(
            "[data-contact-phone-prefix]"
        );


    const phoneDivider =
        modal.querySelector(
            "[data-contact-phone-divider]"
        );

    const startUrl =
        modal.dataset.startUrl;

    const verifyUrl =
        modal.dataset.verifyUrl;

    const resendUrl =
        modal.dataset.resendUrl;


    let mode = null;
    let cooldownTimer = null;
    let busy = false;


    /* =====================================================
       CSRF
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


    /* =====================================================
       HELPERS
       ===================================================== */

    function currentInputForMode() {

        if (mode === "email") {
            return page.querySelector(
                "[data-current-email]"
            );
        }

        if (mode === "phone") {
            return page.querySelector(
                "[data-current-phone]"
            );
        }

        return null;

    }


    function setError(
        element,
        message = ""
    ) {

        if (!element) {
            return;
        }

        element.textContent =
            message;

    }


    function clearErrors() {

        setError(
            entryError,
            ""
        );

        setError(
            verifyError,
            ""
        );

    }


    function setBusy(
        state,
        button = null,
        busyText = "Please wait..."
    ) {

        busy = state;

        [
            sendButton,
            verifyButton,
            ...closeButtons,
        ].forEach(
            (item) => {

                if (item) {
                    item.disabled = state;
                }

            }
        );


        if (
            button
            &&
            state
        ) {

            button.dataset.originalText =
                button.textContent.trim();

            button.textContent =
                busyText;

        }


        if (
            button
            &&
            !state
            &&
            button.dataset.originalText
        ) {

            button.textContent =
                button.dataset.originalText;

            delete button.dataset.originalText;

        }

    }


    async function readJson(
        response
    ) {

        try {
            return await response.json();
        }
        catch (_error) {
            return {
                ok: false,
                message: (
                    "The server returned an invalid response."
                ),
            };
        }

    }


    async function postJson(
        url,
        payload
    ) {

        const response =
            await fetch(
                url,
                {
                    method: "POST",
                    headers: {
                        "Content-Type": (
                            "application/json"
                        ),
                        "X-CSRFToken": (
                            getCsrfToken()
                        ),
                    },
                    body: JSON.stringify(
                        payload
                    ),
                }
            );


        const result =
            await readJson(
                response
            );


        return {
            response,
            result,
        };

    }


    /* =====================================================
       TOAST
       ===================================================== */

    function showToast(
        message
    ) {

        const toast =
            document.createElement(
                "div"
            );

        toast.className =
            "account-contact-toast";

        toast.textContent =
            message;

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
                    180
                );

            },
            2600
        );

    }


    /* =====================================================
       COOLDOWN
       ===================================================== */

    function stopCooldown() {

        if (cooldownTimer) {
            window.clearInterval(
                cooldownTimer
            );
            cooldownTimer = null;
        }

        if (countdown) {
            countdown.textContent = "";
        }

    }


    function startCooldown(
        seconds
    ) {

        stopCooldown();

        let remaining =
            Math.max(
                0,
                Number(seconds) || 0
            );


        function renderCountdown() {

            if (!resendButton) {
                return;
            }

            if (remaining <= 0) {

                resendButton.disabled = false;

                if (countdown) {
                    countdown.textContent = "";
                }

                stopCooldown();

                return;
            }

            resendButton.disabled = true;

            if (countdown) {
                countdown.textContent =
                    `Resend available in ${remaining}s`;
            }

            remaining -= 1;

        }


        renderCountdown();

        cooldownTimer =
            window.setInterval(
                renderCountdown,
                1000
            );

    }


    /* =====================================================
       MODAL STATE
       ===================================================== */

    function showEntryStep() {

        if (entryStep) {
            entryStep.hidden = false;
        }

        if (verifyStep) {
            verifyStep.hidden = true;
        }

    }


    function showVerifyStep(
        maskedValue,
        retryAfter = 60
    ) {

        if (entryStep) {
            entryStep.hidden = true;
        }

        if (verifyStep) {
            verifyStep.hidden = false;
        }

        if (codeMessage) {
            codeMessage.textContent =
                (
                    "We sent a 6-digit verification code to "
                    +
                    maskedValue
                    +
                    "."
                );
        }

        if (codeInput) {
            codeInput.value = "";
        }

        clearErrors();

        startCooldown(
            retryAfter
        );

        window.setTimeout(
            () => {
                codeInput?.focus();
            },
            50
        );

    }


    function configureModal(
        nextMode
    ) {

        mode = nextMode;

        clearErrors();
        stopCooldown();
        showEntryStep();


        const currentInput =
            currentInputForMode();

        const current =
            currentInput?.value
            ||
            "";


        if (currentValue) {
            currentValue.textContent =
                current;
        }


        if (mode === "email") {

            if (title) {
                title.textContent =
                    "Change Email Address";
            }

            if (subtitle) {
                subtitle.textContent =
                    "Enter your new email address. We will verify it before updating your account.";
            }

            if (currentLabel) {
                currentLabel.textContent =
                    "Current Email";
            }

            if (newLabel) {
                newLabel.textContent =
                    "New Email";
            }

            if (valueInput) {

                valueInput.type =
                    "email";

                valueInput.placeholder =
                    "name@example.com";

                valueInput.autocomplete =
                    "email";

                valueInput.inputMode =
                    "email";

                valueInput.maxLength =
                    255;

            }


            valueShell?.classList.remove(
                "is-phone"
            );


            if (phonePrefix) {
                phonePrefix.hidden = true;
            }


            if (phoneDivider) {
                phoneDivider.hidden = true;
            }

        }

        else {

            if (title) {
                title.textContent =
                    "Change Phone Number";
            }

            if (subtitle) {
                subtitle.textContent =
                    "Enter your new Malaysian phone number. We will verify it before updating your account.";
            }

            if (currentLabel) {
                currentLabel.textContent =
                    "Current Phone Number";
            }

            if (newLabel) {
                newLabel.textContent =
                    "New Phone Number";
            }

            if (valueInput) {

                valueInput.type =
                    "tel";

                valueInput.placeholder =
                    "1121720511";

                valueInput.autocomplete =
                    "off";

                valueInput.inputMode =
                    "numeric";

                valueInput.maxLength =
                    12;

            }


            valueShell?.classList.add(
                "is-phone"
            );


            if (phonePrefix) {
                phonePrefix.hidden = false;
            }


            if (phoneDivider) {
                phoneDivider.hidden = false;
            }

        }


        if (valueInput) {
            valueInput.value = "";
        }

        if (codeInput) {
            codeInput.value = "";
        }

    }


    function openModal(
        nextMode
    ) {

        if (
            nextMode !== "email"
            &&
            nextMode !== "phone"
        ) {
            return;
        }

        configureModal(
            nextMode
        );

        modal.hidden = false;

        document.body.style.overflow =
            "hidden";

        window.setTimeout(
            () => {
                valueInput?.focus();
            },
            40
        );

    }


    function closeModal() {

        if (busy) {
            return;
        }

        modal.hidden = true;

        document.body.style.overflow =
            "";

        stopCooldown();
        clearErrors();

        mode = null;

    }


    /* =====================================================
       OPEN / CLOSE EVENTS
       ===================================================== */

    openButtons.forEach(
        (button) => {

            button.addEventListener(
                "click",
                () => {

                    openModal(
                        button.dataset
                            .contactChange
                    );

                }
            );

        }
    );


    closeButtons.forEach(
        (button) => {

            button.addEventListener(
                "click",
                closeModal
            );

        }
    );


    modal.addEventListener(
        "click",
        (event) => {

            if (
                event.target
                ===
                modal
            ) {
                closeModal();
            }

        }
    );


    document.addEventListener(
        "keydown",
        (event) => {

            if (
                event.key === "Escape"
                &&
                !modal.hidden
            ) {
                closeModal();
            }

        }
    );


    /* =====================================================
       SEND INITIAL CODE
       ===================================================== */

    sendButton?.addEventListener(
        "click",
        async () => {

            clearErrors();

            let value =
                valueInput?.value
                    ?.trim()
                ||
                "";


            if (
                mode === "phone"
                &&
                value
            ) {

                /*
                * User only enters the part after +60.
                *
                * Also support pasted formats:
                *
                * 01121720511
                * +601121720511
                * 601121720511
                */

                let digits =
                    value.replace(
                        /\D/g,
                        ""
                    );


                if (
                    digits.startsWith(
                        "60"
                    )
                ) {

                    digits =
                        digits.slice(
                            2
                        );

                }


                if (
                    digits.startsWith(
                        "0"
                    )
                ) {

                    digits =
                        digits.slice(
                            1
                        );

                }


                value =
                    `+60${digits}`;

            }


            if (!value) {

                setError(
                    entryError,
                    (
                        mode === "email"
                            ? "Please enter your new email address."
                            : "Please enter your new phone number."
                    )
                );

                valueInput?.focus();

                return;
            }


            setBusy(
                true,
                sendButton,
                "Sending..."
            );


            try {

                const {
                    response,
                    result,
                } = await postJson(
                    startUrl,
                    {
                        type: mode,
                        value,
                    }
                );


                if (
                    !response.ok
                    ||
                    !result.ok
                ) {

                    if (
                        result.can_resend
                    ) {

                        showVerifyStep(
                            result.masked_value
                                ||
                                value,
                            result.retry_after
                                ||
                                60
                        );

                        setError(
                            verifyError,
                            result.message
                        );

                        return;
                    }

                    throw new Error(
                        result.message
                        ||
                        "Unable to send verification code."
                    );

                }


                showVerifyStep(
                    result.masked_value
                    ||
                    value,
                    result.retry_after
                    ||
                    60
                );

            }

            catch (error) {

                setError(
                    entryError,
                    error.message
                    ||
                    "Unable to send verification code."
                );

            }

            finally {

                setBusy(
                    false,
                    sendButton
                );

            }

        }
    );

    valueInput?.addEventListener(
        "input",
        () => {

            if (
                mode !== "phone"
            ) {
                return;
            }


            let digits =
                valueInput.value
                    .replace(
                        /\D/g,
                        ""
                    );


            /*
            * If user pastes:
            * +601121720511
            */

            if (
                digits.startsWith(
                    "60"
                )
            ) {

                digits =
                    digits.slice(
                        2
                    );

            }


            /*
            * If user pastes:
            * 01121720511
            */

            if (
                digits.startsWith(
                    "0"
                )
            ) {

                digits =
                    digits.slice(
                        1
                    );

            }


            valueInput.value =
                digits;

        }
    );
    /* =====================================================
       VERIFY CODE
       ===================================================== */

    verifyButton?.addEventListener(
        "click",
        async () => {

            setError(
                verifyError,
                ""
            );

            const code =
                String(
                    codeInput?.value
                    ||
                    ""
                )
                .replace(
                    /\D/g,
                    ""
                )
                .slice(
                    0,
                    6
                );


            if (code.length !== 6) {

                setError(
                    verifyError,
                    "Please enter the 6-digit verification code."
                );

                codeInput?.focus();

                return;
            }


            setBusy(
                true,
                verifyButton,
                "Verifying..."
            );


            try {

                const {
                    response,
                    result,
                } = await postJson(
                    verifyUrl,
                    {
                        type: mode,
                        code,
                    }
                );


                if (
                    !response.ok
                    ||
                    !result.ok
                ) {
                    throw new Error(
                        result.message
                        ||
                        "The verification code is not valid."
                    );
                }


                const currentInput =
                    currentInputForMode();


                if (currentInput) {
                    currentInput.value =
                        result.value;
                }


                const successMessage =
                    result.message
                    ||
                    (
                        mode === "email"
                            ? "Email address updated successfully."
                            : "Phone number updated successfully."
                    );


                modal.hidden = true;
                document.body.style.overflow = "";

                stopCooldown();
                clearErrors();

                mode = null;

                showToast(
                    successMessage
                );

            }

            catch (error) {

                setError(
                    verifyError,
                    error.message
                    ||
                    "Unable to verify the code."
                );

                codeInput?.focus();

            }

            finally {

                setBusy(
                    false,
                    verifyButton
                );

            }

        }
    );


    /* =====================================================
       RESEND
       ===================================================== */

    resendButton?.addEventListener(
        "click",
        async () => {

            if (
                resendButton.disabled
                ||
                busy
            ) {
                return;
            }


            setError(
                verifyError,
                ""
            );

            resendButton.disabled = true;
            resendButton.textContent =
                "Sending...";


            try {

                const {
                    response,
                    result,
                } = await postJson(
                    resendUrl,
                    {
                        type: mode,
                    }
                );


                if (
                    !response.ok
                    ||
                    !result.ok
                ) {

                    if (
                        result.retry_after
                    ) {
                        startCooldown(
                            result.retry_after
                        );
                    }

                    throw new Error(
                        result.message
                        ||
                        "Unable to resend the verification code."
                    );

                }


                if (codeMessage) {
                    codeMessage.textContent =
                        (
                            "We sent a new 6-digit verification code to "
                            +
                            (
                                result.masked_value
                                ||
                                "your new contact"
                            )
                            +
                            "."
                        );
                }

                startCooldown(
                    result.retry_after
                    ||
                    60
                );

                codeInput?.focus();

            }

            catch (error) {

                setError(
                    verifyError,
                    error.message
                    ||
                    "Unable to resend the verification code."
                );

            }

            finally {

                resendButton.textContent =
                    "Resend Code";

                if (
                    !cooldownTimer
                ) {
                    resendButton.disabled = false;
                }

            }

        }
    );


    /* =====================================================
       OTP INPUT: NUMBERS ONLY
       ===================================================== */

    codeInput?.addEventListener(
        "input",
        () => {

            codeInput.value =
                codeInput.value
                    .replace(
                        /\D/g,
                        ""
                    )
                    .slice(
                        0,
                        6
                    );

        }
    );


    codeInput?.addEventListener(
        "keydown",
        (event) => {

            if (
                event.key === "Enter"
                &&
                !verifyButton?.disabled
            ) {

                event.preventDefault();
                verifyButton?.click();

            }

        }
    );


    valueInput?.addEventListener(
        "keydown",
        (event) => {

            if (
                event.key === "Enter"
                &&
                !sendButton?.disabled
            ) {

                event.preventDefault();
                sendButton?.click();

            }

        }
    );

})();
