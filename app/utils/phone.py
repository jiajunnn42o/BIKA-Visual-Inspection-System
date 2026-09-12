import phonenumbers

from phonenumbers import (
    PhoneNumberFormat,
    PhoneNumberType,
)


class InvalidPhoneNumberError(ValueError):
    pass


def normalize_malaysian_mobile(
    raw_phone,
):
    """
    Validate a Malaysian mobile number and
    return it in E.164 format.

    Examples:
        0123456789
        012-345 6789
        +60123456789

    Stored result:
        +60123456789
    """

    if not raw_phone:
        raise InvalidPhoneNumberError(
            "Phone number is required."
        )

    raw_phone = raw_phone.strip()

    try:
        number = phonenumbers.parse(
            raw_phone,
            "MY",
        )

    except phonenumbers.NumberParseException:
        raise InvalidPhoneNumberError(
            "Please enter a valid Malaysian mobile number."
        )

    # Must actually belong to Malaysia.
    region = (
        phonenumbers.region_code_for_number(
            number
        )
    )

    if region != "MY":
        raise InvalidPhoneNumberError(
            "Only Malaysian mobile numbers are supported."
        )

    if not phonenumbers.is_possible_number(
        number
    ):
        raise InvalidPhoneNumberError(
            "This Malaysian mobile number is not possible."
        )

    if not phonenumbers.is_valid_number(
        number
    ):
        raise InvalidPhoneNumberError(
            "Please enter a valid Malaysian mobile number."
        )

    number_type = (
        phonenumbers.number_type(
            number
        )
    )

    if number_type not in {
        PhoneNumberType.MOBILE,
        PhoneNumberType.FIXED_LINE_OR_MOBILE,
    }:
        raise InvalidPhoneNumberError(
            "Please enter a Malaysian mobile number."
        )

    return phonenumbers.format_number(
        number,
        PhoneNumberFormat.E164,
    )