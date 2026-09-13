from flask import current_app


def send_phone_verification_code_sms(
    user,
    code,
):
    """
    Send or simulate a phone verification OTP.

    Development:
        Prints OTP to the Flask terminal.

    Future production:
        A real SMS provider can be connected here.
    """

    sms_mode = current_app.config.get(
        "SMS_MODE",
        "console",
    )

    # =====================================================
    # DEVELOPMENT / FYP DEMO MODE
    # =====================================================

    if sms_mode == "console":

        masked_phone = _mask_phone(
            user.phone_number
        )

        current_app.logger.warning(
            "\n"
            "========================================\n"
            "BIKA PHONE VERIFICATION - DEVELOPMENT\n"
            "========================================\n"
            f"Phone: {masked_phone}\n"
            f"OTP:   {code}\n"
            "Expires in: 5 minutes\n"
            "========================================"
        )

        return True

    # =====================================================
    # UNKNOWN MODE
    # =====================================================

    raise RuntimeError(
        f"Unsupported SMS_MODE: {sms_mode}"
    )


def _mask_phone(
    phone_number,
):
    """
    Mask phone number for logs.

    Example:
        +60123456789
        ->
        +6012****6789
    """

    if not phone_number:
        return "Unknown"

    if len(phone_number) <= 8:
        return "****"

    return (
        f"{phone_number[:5]}"
        f"****"
        f"{phone_number[-4:]}"
    )