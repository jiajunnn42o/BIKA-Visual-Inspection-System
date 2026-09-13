import re

import phonenumbers

from phonenumbers import (
    PhoneNumberFormat,
    PhoneNumberType,
)


class InvalidPhoneNumberError(
    ValueError
):
    pass


def normalize_malaysian_mobile(
    raw_phone,
):
    """
    Validate and normalize a Malaysian
    mobile phone number.

    Accepted examples:

        12 345 6789
        012 345 6789
        012-345 6789
        60123456789
        +60123456789

    Stored format:

        +60123456789
    """

    if not raw_phone:

        raise InvalidPhoneNumberError(
            "Phone number is required."
        )


    raw_phone = (
        raw_phone
        .strip()
    )


    # Remove spaces, hyphens, brackets, etc.
    digits = re.sub(
        r"\D",
        "",
        raw_phone,
    )


    if not digits:

        raise InvalidPhoneNumberError(
            (
                "Please enter a valid "
                "Malaysian mobile number."
            )
        )


    # =====================================================
    # CONVERT TO INTERNATIONAL MALAYSIA FORMAT
    # =====================================================

    if raw_phone.startswith("+60"):

        candidate = (
            "+"
            + digits
        )

    elif digits.startswith("60"):

        candidate = (
            "+"
            + digits
        )

    elif digits.startswith("0"):

        candidate = (
            "+60"
            + digits[1:]
        )

    else:

        # Register UI uses a fixed +60 prefix,
        # so users normally enter:
        #
        # 12 345 6789
        #
        candidate = (
            "+60"
            + digits
        )


    # =====================================================
    # PARSE NUMBER
    # =====================================================

    try:

        parsed = (
            phonenumbers.parse(
                candidate,
                None,
            )
        )

    except phonenumbers.NumberParseException:

        raise InvalidPhoneNumberError(
            (
                "Please enter a valid "
                "Malaysian mobile number."
            )
        )


    # =====================================================
    # COUNTRY CHECK
    # =====================================================

    if (
        parsed.country_code
        != 60
    ):

        raise InvalidPhoneNumberError(
            (
                "Only Malaysian phone "
                "numbers are supported."
            )
        )


    # =====================================================
    # VALIDITY CHECK
    # =====================================================

    if (
        not phonenumbers.is_possible_number(
            parsed
        )
        or
        not phonenumbers.is_valid_number(
            parsed
        )
    ):

        raise InvalidPhoneNumberError(
            (
                "Please enter a valid "
                "Malaysian mobile number."
            )
        )


    # =====================================================
    # MOBILE NUMBER CHECK
    # =====================================================

    number_type = (
        phonenumbers.number_type(
            parsed
        )
    )


    allowed_types = {
        PhoneNumberType.MOBILE,
        PhoneNumberType.FIXED_LINE_OR_MOBILE,
    }


    if (
        number_type
        not in allowed_types
    ):

        raise InvalidPhoneNumberError(
            (
                "Please enter a valid "
                "Malaysian mobile number."
            )
        )


    # =====================================================
    # NORMALIZE TO E.164
    # =====================================================

    return (
        phonenumbers.format_number(
            parsed,
            PhoneNumberFormat.E164,
        )
    )