from datetime import (

    datetime,

    timezone,

)



import re


from pathlib import Path



from uuid import uuid4



from zoneinfo import ZoneInfo





from flask import (

    current_app,

    flash,

    jsonify,

    redirect,

    render_template,

    request,

    url_for,

)



from flask_login import (

    current_user,

    login_required,

)



from sqlalchemy.exc import (

    IntegrityError,

    SQLAlchemyError,

)








from app.account import (

    account_bp,

)



from app.account.forms import (

    PasswordChangeForm,

    PersonalInformationForm,

)



from app.extensions import db



from app.models import (

    User,

    UserRole,

    UserStatus,

)



from app.workflow_models import (

    UserNotificationPreference,

    WorkInformationChangeRequest,

)



from app.services.email_service import (

    send_password_changed_email,

)



from app.services.notification_service import (

    email_notifications_enabled,

    get_notification_preferences,

    notify_superadmins_of_work_request,

)



from app.services.work_request_email_service import (

    send_work_information_request_email,

)



from app.services.contact_change_service import (

    ContactChangeError,

    ContactChangeRateLimitError,

    RESEND_COOLDOWN_SECONDS,

    mask_contact_value,

    resend_contact_change,

    send_contact_change_code,

    start_contact_change,

    verify_contact_change,

)


from app.utils.phone import (

    InvalidPhoneNumberError,

    normalize_malaysian_mobile,

)


from PIL import (

    Image,

    UnidentifiedImageError,

)



from app.superadmin.forms import (

    DEPARTMENT_CHOICES,

    JOB_TITLE_CHOICES,

    SHIFT_CHOICES,

)





MALAYSIA_TZ = ZoneInfo(

    "Asia/Kuala_Lumpur"

)










# =========================================================

# LABELS

# =========================================================



def _role_label(

    role,

):

    labels = {

        "superadmin":

            "SuperAdmin",



        "admin":

            "Admin",



        "user":

            "User",

    }



    return labels.get(

        role,

        str(

            role

            or

            ""

        ).title(),

    )





def _status_label(

    status,

):

    labels = {

        "active":

            "Active",



        "pending":

            "Pending",



        "disabled":

            "Disabled",



        "locked":

            "Locked",



        "rejected":

            "Rejected",

    }



    return labels.get(

        status,

        str(

            status

            or

            ""

        ).title(),

    )





# =========================================================

# TIME

# =========================================================



def _to_malaysia_time(

    value,

):

    if value is None:

        return None



    if value.tzinfo is None:

        value = value.replace(

            tzinfo=timezone.utc

        )



    return value.astimezone(

        MALAYSIA_TZ

    )





def _member_since_label(

    value,

):

    value = _to_malaysia_time(

        value

    )



    if value is None:

        return "—"



    return value.strftime(

        "%b %Y"

    )





def _last_login_label(

    value,

):

    value = _to_malaysia_time(

        value

    )



    if value is None:

        return "—"



    now = datetime.now(

        MALAYSIA_TZ

    )



    if (

        value.date()

        ==

        now.date()

    ):

        return value.strftime(

            "Today, %H:%M"

        )



    return value.strftime(

        "%d %b %Y, %H:%M"

    )





def _request_time_label(

    value,

):

    value = _to_malaysia_time(

        value

    )



    if value is None:

        return "—"



    return value.strftime(

        "%d %b %Y, %H:%M"

    )





# =========================================================

# SESSION

# =========================================================



def _detect_device_label():



    user_agent = (

        request.headers.get(

            "User-Agent",

            "",

        )

        or

        ""

    )



    ua = user_agent.lower()



    if "windows" in ua:

        os_name = "Windows"



    elif (

        "mac os" in ua

        or

        "macintosh" in ua

    ):

        os_name = "macOS"



    elif (

        "iphone" in ua

        or

        "ipad" in ua

    ):

        os_name = "iOS"



    elif "android" in ua:

        os_name = "Android"



    elif "linux" in ua:

        os_name = "Linux"



    else:

        os_name = "Device"



    if "edg/" in ua:

        browser_name = "Edge"



    elif (

        "chrome/" in ua

        and

        "edg/" not in ua

    ):

        browser_name = "Chrome"



    elif "firefox/" in ua:

        browser_name = "Firefox"



    elif (

        "safari/" in ua

        and

        "chrome/" not in ua

    ):

        browser_name = "Safari"



    else:

        browser_name = "Browser"



    return (

        f"{os_name} · "

        f"{browser_name}"

    )





def _current_session_view():



    return {

        "device":

            _detect_device_label(),



        "meta":

            "This device",



        "is_current":

            True,



        "icon":

            "monitor",

    }





# =========================================================

# PROFILE PHOTO

# =========================================================



def _profile_photo_url(

    user,

):

    if not user.profile_photo:

        return None



    return url_for(

        "static",

        filename=user.profile_photo,

    )





# =========================================================

# WORK INFORMATION

# =========================================================



def _choice_with_current(

    choices,

    current_value,

):

    """

    Keep legacy/current values such as:

        System Owner

        N/A



    so existing SuperAdmin data is not lost.

    """



    result = list(

        choices

    )



    current_value = str(

        current_value

        or

        ""

    ).strip()



    if not current_value:

        return result



    values = {

        value

        for value, _label

        in result

    }



    if (

        current_value

        not in values

    ):

        position = (

            1

            if (

                result

                and

                result[0][0]

                ==

                ""

            )

            else

            0

        )



        result.insert(

            position,

            (

                current_value,

                current_value,

            ),

        )



    return result





def _value_allowed(

    value,

    choices,

):

    return any(

        (

            option_value

            ==

            value

            and

            option_value

            !=

            ""

        )

        for (

            option_value,

            _label,

        )

        in choices

    )





def _get_pending_work_request(

    user_id,

):

    return db.session.scalar(

        db.select(

            WorkInformationChangeRequest

        )

        .where(

            WorkInformationChangeRequest.user_id

            ==

            user_id,



            WorkInformationChangeRequest.status

            ==

            "pending",

        )

        .order_by(

            WorkInformationChangeRequest

            .created_at

            .desc()

        )

        .limit(1)

    )





def _employee_id_used_by_user(

    employee_id,

    current_user_id,

):

    existing_id = db.session.scalar(

        db.select(

            User.id

        )

        .where(

            db.func.upper(

                User.employee_id

            )

            ==

            employee_id.upper(),



            User.id

            !=

            current_user_id,

        )

        .limit(1)

    )



    return (

        existing_id

        is not None

    )





def _employee_id_reserved_by_request(

    employee_id,

    current_user_id,

):

    existing_request_id = (

        db.session.scalar(

            db.select(

                WorkInformationChangeRequest.id

            )

            .where(

                WorkInformationChangeRequest.status

                ==

                "pending",



                db.func.upper(

                    WorkInformationChangeRequest

                    .new_employee_id

                )

                ==

                employee_id.upper(),



                WorkInformationChangeRequest.user_id

                !=

                current_user_id,

            )

            .limit(1)

        )

    )



    return (

        existing_request_id

        is not None

    )





# =========================================================

# ACCOUNT PAGE

# =========================================================



@account_bp.route(

    "",

    methods=[

        "GET",

    ],

)

@login_required

def index():



    personal_form = (

        PersonalInformationForm(

            current_user_id=current_user.id,

            obj=current_user,

        )

    )



    password_form = (

        PasswordChangeForm()

    )



    is_superadmin = (

        current_user.role

        ==

        UserRole.SUPERADMIN.value

    )





    # SuperAdmin edits are applied immediately,

    # therefore their old self-submitted test request

    # must not lock the Account UI.

    pending_work_request = (

        None

        if is_superadmin

        else

        _get_pending_work_request(

            current_user.id

        )

    )



    pending_changes = []



    pending_submitted_at = None



    if pending_work_request:



        pending_changes = (

            pending_work_request

            .changed_fields()

        )



        pending_submitted_at = (

            _request_time_label(

                pending_work_request

                .created_at

            )

        )



    work_department_choices = (

        _choice_with_current(

            DEPARTMENT_CHOICES,

            current_user.department,

        )

    )



    work_shift_choices = (

        _choice_with_current(

            SHIFT_CHOICES,

            current_user.shift,

        )

    )



    work_job_title_choices = (

        _choice_with_current(

            JOB_TITLE_CHOICES,

            current_user.job_title,

        )

    )



    notification_preferences = (

        get_notification_preferences(

            current_user.id,

            create=True,

        )

    )





    try:

        db.session.commit()



    except SQLAlchemyError:



        db.session.rollback()



        current_app.logger.exception(

            "Unable to initialize notification preferences."

        )





        notification_preferences = (

            UserNotificationPreference(

                user_id=current_user.id,

                email_notifications=True,

                in_app_alerts=True,

            )

        )



    return render_template(

        "account/account.html",



        user=current_user,



        personal_form=personal_form,



        password_form=password_form,



        notification_preferences=(

            notification_preferences

        ),



        role_label=(

            _role_label(

                current_user.role

            )





        ),



        status_label=(

            _status_label(

                current_user.status

            )

        ),



        member_since=(

            _member_since_label(

                current_user.created_at

            )

        ),



        last_login=(

            _last_login_label(

                current_user.last_login_at

            )

        ),



        profile_photo_url=(

            _profile_photo_url(

                current_user

            )

        ),



        active_sessions=[

            _current_session_view(),

        ],



        pending_work_request=(

            pending_work_request

        ),



        pending_changes=(

            pending_changes

        ),



        pending_submitted_at=(

            pending_submitted_at

        ),



        work_department_choices=(

            work_department_choices

        ),



        work_shift_choices=(

            work_shift_choices

        ),



        work_job_title_choices=(

            work_job_title_choices

        ),



        work_requires_approval=(

            not is_superadmin

        ),

    )





# =========================================================

# CHECK USERNAME

# =========================================================



@account_bp.route(

    "/check-username",

    methods=[

        "GET",

    ],

)

@login_required

def check_username_availability():



    username = (

        request.args.get(

            "username",

            "",

        )

        .strip()

        .lower()

    )



    if not username:

        return jsonify(

            available=False,

            message="Required",

        )



    if len(username) < 3:

        return jsonify(

            available=False,

            message="At least 3 characters",

        )



    if len(username) > 100:

        return jsonify(

            available=False,

            message="Too long",

        )



    existing_id = db.session.scalar(

        db.select(

            User.id

        )

        .where(

            db.func.lower(

                User.username

            )

            ==

            username,



            User.id

            !=

            current_user.id,

        )

        .limit(1)

    )



    if existing_id is not None:

        return jsonify(

            available=False,

            message="Already in use",

        )



    return jsonify(

        available=True,

        message="Available",

    )





# =========================================================

# CHECK EMPLOYEE ID

# =========================================================



@account_bp.route(

    "/check-employee-id",

    methods=[

        "GET",

    ],

)

@login_required

def check_employee_id_availability():



    employee_id = (

        request.args.get(

            "employee_id",

            "",

        )

        .strip()

        .upper()

    )



    if not employee_id:

        return jsonify(

            available=False,

            message="Required",

        )



    if len(employee_id) > 80:

        return jsonify(

            available=False,

            message="Too long",

        )



    if (

        _employee_id_used_by_user(

            employee_id,

            current_user.id,

        )

    ):

        return jsonify(

            available=False,

            message="Already in use",

        )



    if (

        _employee_id_reserved_by_request(

            employee_id,

            current_user.id,

        )

    ):

        return jsonify(

            available=False,

            message="Pending request already uses this ID",

        )



    return jsonify(

        available=True,

        message="Available",

    )





# =========================================================

# PERSONAL INFORMATION

# =========================================================



@account_bp.route(

    "/personal-information",

    methods=[

        "POST",

    ],

)

@login_required

def update_personal_information():



    form = PersonalInformationForm(

        current_user_id=current_user.id,

    )



    if not form.validate_on_submit():



        for field_errors in (

            form.errors.values()

        ):

            for error in field_errors:

                flash(

                    error,

                    "error",

                )



        return redirect(

            url_for(

                "account.index"

            )

        )



    first_name = (

        form.first_name.data

        .strip()

    )



    last_name = (

        form.last_name.data

        .strip()

    )



    username = (

        form.username.data

        .strip()

        .lower()

    )



    current_user.first_name = (

        first_name

    )



    current_user.last_name = (

        last_name

    )



    current_user.username = (

        username

    )



    try:

        db.session.commit()



    except IntegrityError:



        db.session.rollback()



        flash(

            "This username is already in use.",

            "error",

        )



        return redirect(

            url_for(

                "account.index"

            )

        )



    except SQLAlchemyError:



        db.session.rollback()



        current_app.logger.exception(

            "Unable to update account profile."

        )



        flash(

            (

                "Your personal information "

                "could not be saved."

            ),

            "error",

        )



        return redirect(

            url_for(

                "account.index"

            )

        )



    flash(

        (

            "Personal information saved "

            "successfully."

        ),

        "success",

    )



    return redirect(

        url_for(

            "account.index",

            saved="profile",

        )

    )





# =========================================================

# CONTACT CHANGE HELPERS

# =========================================================


def _normalize_contact_change_value(
    change_type,
    raw_value,
):

    raw_value = str(
        raw_value
        or
        ""
    ).strip()

    if change_type == "email":

        value = raw_value.lower()

        if (
            not value
            or
            len(value) > 255
            or
            not re.fullmatch(
                r"[^\s@]+@[^\s@]+\.[^\s@]+",
                value,
            )
        ):
            raise ContactChangeError(
                "Please enter a valid email address."
            )

        return value

    if change_type == "phone":

        try:
            return normalize_malaysian_mobile(
                raw_value
            )

        except InvalidPhoneNumberError as exc:
            raise ContactChangeError(
                str(exc)
            ) from exc

    raise ContactChangeError(
        "Invalid contact change type."
    )



def _contact_change_active_account_error():

    if (
        current_user.status
        ==
        UserStatus.ACTIVE.value
    ):
        return None

    return jsonify(
        ok=False,
        message=(
            "Only active accounts can change "
            "their email address or phone number."
        ),
    ), 403


# =========================================================

# START EMAIL / PHONE CHANGE

# =========================================================


@account_bp.route(
    "/contact-change/start",
    methods=["POST"],
)
@login_required
def start_account_contact_change():

    inactive_response = (
        _contact_change_active_account_error()
    )

    if inactive_response is not None:
        return inactive_response

    data = request.get_json(
        silent=True
    ) or {}

    change_type = str(
        data.get(
            "type",
            "",
        )
    ).strip().lower()

    try:
        pending_value = (
            _normalize_contact_change_value(
                change_type,
                data.get(
                    "value",
                    "",
                ),
            )
        )

        change, code = (
            start_contact_change(
                current_user,
                change_type,
                pending_value,
            )
        )

        db.session.commit()

    except ContactChangeRateLimitError as exc:

        db.session.rollback()

        return jsonify(
            ok=False,
            message=str(exc),
            retry_after=exc.retry_after,
        ), 429

    except ContactChangeError as exc:

        db.session.rollback()

        return jsonify(
            ok=False,
            message=str(exc),
        ), 400

    except IntegrityError:

        db.session.rollback()

        return jsonify(
            ok=False,
            message=(
                "That email address or phone number "
                "is already in use or already waiting "
                "for verification."
            ),
        ), 409

    except SQLAlchemyError:

        db.session.rollback()

        current_app.logger.exception(
            "Unable to start account contact change."
        )

        return jsonify(
            ok=False,
            message=(
                "The verification could not be started. "
                "Please try again."
            ),
        ), 500

    try:
        send_contact_change_code(
            current_user,
            change,
            code,
        )

    except Exception:

        current_app.logger.exception(
            (
                "Contact verification code could not "
                "be delivered for user %s."
            ),
            current_user.id,
        )

        return jsonify(
            ok=False,
            message=(
                "The verification code was created, "
                "but it could not be delivered. "
                "Please use Resend Code shortly."
            ),
            retry_after=RESEND_COOLDOWN_SECONDS,
            can_resend=True,
            masked_value=mask_contact_value(
                change_type,
                pending_value,
            ),
        ), 502

    return jsonify(
        ok=True,
        message="Verification code sent.",
        type=change_type,
        masked_value=mask_contact_value(
            change_type,
            pending_value,
        ),
        retry_after=RESEND_COOLDOWN_SECONDS,
    )


# =========================================================

# VERIFY EMAIL / PHONE CHANGE

# =========================================================


@account_bp.route(
    "/contact-change/verify",
    methods=["POST"],
)
@login_required
def verify_account_contact_change():

    inactive_response = (
        _contact_change_active_account_error()
    )

    if inactive_response is not None:
        return inactive_response

    data = request.get_json(
        silent=True
    ) or {}

    change_type = str(
        data.get(
            "type",
            "",
        )
    ).strip().lower()

    code = str(
        data.get(
            "code",
            "",
        )
    ).strip()

    if not re.fullmatch(
        r"\d{6}",
        code,
    ):
        return jsonify(
            ok=False,
            message=(
                "Please enter the 6-digit "
                "verification code."
            ),
        ), 400

    try:
        result = verify_contact_change(
            current_user,
            change_type,
            code,
        )

        db.session.commit()

    except IntegrityError:

        db.session.rollback()

        return jsonify(
            ok=False,
            message=(
                "That email address or phone number "
                "is already in use."
            ),
        ), 409

    except SQLAlchemyError:

        db.session.rollback()

        current_app.logger.exception(
            "Unable to verify account contact change."
        )

        return jsonify(
            ok=False,
            message=(
                "The verification could not be completed. "
                "Please try again."
            ),
        ), 500

    if not result.get("ok"):
        return jsonify(**result), 400

    return jsonify(**result)


# =========================================================

# RESEND EMAIL / PHONE CHANGE OTP

# =========================================================


@account_bp.route(
    "/contact-change/resend",
    methods=["POST"],
)
@login_required
def resend_account_contact_change():

    inactive_response = (
        _contact_change_active_account_error()
    )

    if inactive_response is not None:
        return inactive_response

    data = request.get_json(
        silent=True
    ) or {}

    change_type = str(
        data.get(
            "type",
            "",
        )
    ).strip().lower()

    try:
        change, code = (
            resend_contact_change(
                current_user,
                change_type,
            )
        )

        db.session.commit()

    except ContactChangeRateLimitError as exc:

        db.session.rollback()

        return jsonify(
            ok=False,
            message=str(exc),
            retry_after=exc.retry_after,
        ), 429

    except ContactChangeError as exc:

        db.session.rollback()

        return jsonify(
            ok=False,
            message=str(exc),
        ), 400

    except SQLAlchemyError:

        db.session.rollback()

        current_app.logger.exception(
            "Unable to regenerate account contact OTP."
        )

        return jsonify(
            ok=False,
            message=(
                "A new verification code could not be created."
            ),
        ), 500

    try:
        send_contact_change_code(
            current_user,
            change,
            code,
        )

    except Exception:

        current_app.logger.exception(
            (
                "Resent contact verification code could "
                "not be delivered for user %s."
            ),
            current_user.id,
        )

        return jsonify(
            ok=False,
            message=(
                "The new verification code was created, "
                "but it could not be delivered."
            ),
            retry_after=RESEND_COOLDOWN_SECONDS,
        ), 502

    return jsonify(
        ok=True,
        message="A new verification code was sent.",
        type=change_type,
        masked_value=mask_contact_value(
            change_type,
            change.pending_value,
        ),
        retry_after=RESEND_COOLDOWN_SECONDS,
    )


# =========================================================

# SUBMIT WORK INFORMATION REQUEST

# =========================================================



# =========================================================

# SAVE / SUBMIT WORK INFORMATION

# =========================================================



@account_bp.route(

    "/work-information",

    methods=[

        "POST",

    ],

)

@login_required

def submit_work_information_request():



    # =====================================================

    # ACTIVE ACCOUNT ONLY

    # =====================================================



    if (

        current_user.status

        !=

        UserStatus.ACTIVE.value

    ):



        flash(

            (

                "Only active accounts can update "

                "work information."

            ),

            "error",

        )



        return redirect(

            url_for(

                "account.index"

            )

        )





    # =====================================================

    # ROLE MODE

    # =====================================================



    is_superadmin = (

        current_user.role

        ==

        UserRole.SUPERADMIN.value

    )





    # =====================================================

    # NORMAL USER / ADMIN:

    # ONLY ONE PENDING REQUEST

    # =====================================================



    if not is_superadmin:



        existing_pending = (

            _get_pending_work_request(

                current_user.id

            )

        )



        if existing_pending:



            flash(

                (

                    "You already have a work information "

                    "request waiting for review."

                ),

                "error",

            )



            return redirect(

                url_for(

                    "account.index"

                )

            )





    # =====================================================

    # NORMALIZE VALUES

    # =====================================================



    employee_id = (

        request.form.get(

            "employee_id",

            "",

        )

        .strip()

        .upper()

    )





    department = (

        request.form.get(

            "department",

            "",

        )

        .strip()

    )





    shift = (

        request.form.get(

            "shift",

            "",

        )

        .strip()

    )





    job_title = (

        request.form.get(

            "job_title",

            "",

        )

        .strip()

    )





    # =====================================================

    # EMPLOYEE ID VALIDATION

    # =====================================================



    if not employee_id:



        flash(

            "Employee ID is required.",

            "error",

        )



        return redirect(

            url_for(

                "account.index"

            )

        )





    if (

        len(employee_id)

        >

        80

    ):



        flash(

            "Employee ID is too long.",

            "error",

        )



        return redirect(

            url_for(

                "account.index"

            )

        )





    if (

        _employee_id_used_by_user(

            employee_id,

            current_user.id,

        )

    ):



        flash(

            (

                "This Employee ID is already "

                "in use."

            ),

            "error",

        )



        return redirect(

            url_for(

                "account.index"

            )

        )





    # Prevent both SuperAdmin direct-save and

    # normal requests from taking an Employee ID

    # already reserved by someone else's pending request.

    if (

        _employee_id_reserved_by_request(

            employee_id,

            current_user.id,

        )

    ):



        flash(

            (

                "This Employee ID is already "

                "reserved by another pending request."

            ),

            "error",

        )



        return redirect(

            url_for(

                "account.index"

            )

        )





    # =====================================================

    # VALID CHOICES

    # =====================================================



    department_choices = (

        _choice_with_current(

            DEPARTMENT_CHOICES,

            current_user.department,

        )

    )





    shift_choices = (

        _choice_with_current(

            SHIFT_CHOICES,

            current_user.shift,

        )

    )





    job_title_choices = (

        _choice_with_current(

            JOB_TITLE_CHOICES,

            current_user.job_title,

        )

    )





    if not _value_allowed(

        department,

        department_choices,

    ):



        flash(

            "Please select a valid Department.",

            "error",

        )



        return redirect(

            url_for(

                "account.index"

            )

        )





    if not _value_allowed(

        shift,

        shift_choices,

    ):



        flash(

            "Please select a valid Shift.",

            "error",

        )



        return redirect(

            url_for(

                "account.index"

            )

        )





    if not _value_allowed(

        job_title,

        job_title_choices,

    ):



        flash(

            "Please select a valid Job Title.",

            "error",

        )



        return redirect(

            url_for(

                "account.index"

            )

        )





    # =====================================================

    # DETECT CHANGES

    # =====================================================



    has_changes = any(

        (

            (

                current_user.employee_id

                or

                ""

            )

            !=

            employee_id,



            (

                current_user.department

                or

                ""

            )

            !=

            department,



            (

                current_user.shift

                or

                ""

            )

            !=

            shift,



            (

                current_user.job_title

                or

                ""

            )

            !=

            job_title,

        )

    )





    if not has_changes:



        flash(

            (

                "No changes were detected in "

                "your work information."

            ),

            "error",

        )



        return redirect(

            url_for(

                "account.index"

            )

        )





    # =====================================================

    # SUPERADMIN

    #

    # DIRECT APPLY.

    # NO APPROVAL.

    # NO EMAIL TO SELF.

    # NO NEW REQUEST.

    # =====================================================



    if is_superadmin:



        # -----------------------------------------------

        # Clean up an old self-submitted pending request

        # created before the direct-save rule existed.

        # -----------------------------------------------



        old_pending = (

            _get_pending_work_request(

                current_user.id

            )

        )





        if old_pending:



            old_pending.status = (

                "cancelled"

            )



            old_pending.cancelled_at = (

                datetime.now(

                    timezone.utc

                )

            )





        # -----------------------------------------------

        # APPLY DIRECTLY

        # -----------------------------------------------



        current_user.employee_id = (

            employee_id

        )



        current_user.department = (

            department

        )



        current_user.shift = (

            shift

        )



        current_user.job_title = (

            job_title

        )





        try:



            db.session.commit()





        except IntegrityError:



            db.session.rollback()



            flash(

                (

                    "The work information could "

                    "not be saved because one of "

                    "the values is already in use."

                ),

                "error",

            )



            return redirect(

                url_for(

                    "account.index"

                )

            )





        except SQLAlchemyError:



            db.session.rollback()



            current_app.logger.exception(

                (

                    "Unable to directly update "

                    "SuperAdmin work information."

                )

            )



            flash(

                (

                    "Your work information "

                    "could not be saved."

                ),

                "error",

            )



            return redirect(

                url_for(

                    "account.index"

                )

            )





        flash(

            (

                "Work information saved "

                "successfully."

            ),

            "success",

        )





        return redirect(

            url_for(

                "account.index",

                saved="work",

            )

        )





    # =====================================================

    # USER / ADMIN

    #

    # CREATE PENDING REQUEST.

    # DO NOT MODIFY USERS TABLE.

    # =====================================================



    work_request = (

        WorkInformationChangeRequest(



            user_id=(

                current_user.id

            ),



            requested_by_id=(

                current_user.id

            ),



            old_employee_id=(

                current_user.employee_id

            ),



            new_employee_id=(

                employee_id

            ),



            old_department=(

                current_user.department

            ),



            new_department=(

                department

            ),



            old_shift=(

                current_user.shift

            ),



            new_shift=(

                shift

            ),



            old_job_title=(

                current_user.job_title

            ),



            new_job_title=(

                job_title

            ),



            status="pending",

        )

    )





    db.session.add(

        work_request

    )





    try:



        db.session.flush()





        superadmins = (

            notify_superadmins_of_work_request(

                work_request

            )

        )





        db.session.commit()





    except IntegrityError:



        db.session.rollback()



        current_app.logger.exception(

            (

                "Work information request "

                "failed due to uniqueness conflict."

            )

        )



        flash(

            (

                "The request could not be submitted "

                "because one of the values is "

                "already in use."

            ),

            "error",

        )



        return redirect(

            url_for(

                "account.index"

            )

        )





    except SQLAlchemyError:



        db.session.rollback()



        current_app.logger.exception(

            (

                "Unable to create work "

                "information request."

            )

        )



        flash(

            (

                "Your work information request "

                "could not be submitted."

            ),

            "error",

        )



        return redirect(

            url_for(

                "account.index"

            )

        )





    # =====================================================

    # EMAIL SUPERADMINS

    # =====================================================



    for superadmin in superadmins:



        if not email_notifications_enabled(

            superadmin.id

        ):

            continue





        try:



            send_work_information_request_email(

                recipient=superadmin,

                requester=current_user,

                work_request=work_request,

            )





        except Exception:



            current_app.logger.exception(

                (

                    "Work information request was "

                    "created but email to "

                    "SuperAdmin %s failed."

                ),

                superadmin.id,

            )





    flash(

        (

            "Changes submitted successfully. "

            "Waiting for SuperAdmin approval."

        ),

        "success",

    )





    return redirect(

        url_for(

            "account.index",

            submitted="work",

        )

    )



# =========================================================

# PASSWORD

# =========================================================



@account_bp.route(

    "/password",

    methods=[

        "POST",

    ],

)

@login_required

def change_password():



    form = PasswordChangeForm()



    if not form.validate_on_submit():



        for field_errors in (

            form.errors.values()

        ):

            for error in field_errors:

                flash(

                    error,

                    "error",

                )



        return redirect(

            url_for(

                "account.index"

            )

        )



    if not current_user.check_password(

        form.current_password.data

    ):

        flash(

            (

                "Current password is "

                "incorrect."

            ),

            "error",

        )



        return redirect(

            url_for(

                "account.index"

            )

        )



    if current_user.check_password(

        form.new_password.data

    ):

        flash(

            (

                "Your new password must be "

                "different from your current "

                "password."

            ),

            "error",

        )



        return redirect(

            url_for(

                "account.index"

            )

        )



    current_user.set_password(

        form.new_password.data

    )



    current_user.password_changed_at = (

        datetime.now(

            timezone.utc

        )

    )



    try:

        db.session.commit()



    except SQLAlchemyError:



        db.session.rollback()



        current_app.logger.exception(

            "Unable to update account password."

        )



        flash(

            (

                "Your password could not "

                "be changed."

            ),

            "error",

        )



        return redirect(

            url_for(

                "account.index"

            )

        )



    try:

        send_password_changed_email(

            user=current_user

        )



    except Exception:

        current_app.logger.exception(

            (

                "Password changed but "

                "notification email could "

                "not be sent."

            )

        )



    flash(

        (

            "Password changed successfully."

        ),

        "success",

    )



    return redirect(

        url_for(

            "account.index",

            saved="password",

        )

    )





# =========================================================

# NOTIFICATION PREFERENCES

# =========================================================



@account_bp.route(

    "/notification-preferences",

    methods=[

        "POST",

    ],

)

@login_required

def update_notification_preferences():



    data = (

        request.get_json(

            silent=True

        )

        or

        {}

    )





    preference_name = (

        str(

            data.get(

                "preference",

                "",

            )

        )

        .strip()

        .lower()

    )





    enabled = data.get(

        "enabled"

    )





    # =====================================================

    # VALIDATE PREFERENCE

    # =====================================================



    allowed_preferences = {

        "email_notifications",

        "in_app_alerts",

    }





    if (

        preference_name

        not in

        allowed_preferences

    ):



        return jsonify(

            ok=False,

            message="Invalid notification preference.",

        ), 400





    # =====================================================

    # VALIDATE BOOLEAN

    # =====================================================



    if (

        not isinstance(

            enabled,

            bool,

        )

    ):



        return jsonify(

            ok=False,

            message="Invalid preference value.",

        ), 400





    # =====================================================

    # GET / CREATE CURRENT USER PREFERENCES

    # =====================================================



    preferences = (

        db.session.get(

            UserNotificationPreference,

            current_user.id,

        )

    )





    if (

        preferences is None

    ):



        preferences = (

            UserNotificationPreference(



                user_id=(

                    current_user.id

                ),



                email_notifications=True,



                in_app_alerts=True,

            )

        )





        db.session.add(

            preferences

        )





    # =====================================================

    # UPDATE ONLY CURRENT USER

    # =====================================================



    if (

        preference_name

        ==

        "email_notifications"

    ):



        preferences.email_notifications = (

            enabled

        )





    elif (

        preference_name

        ==

        "in_app_alerts"

    ):



        preferences.in_app_alerts = (

            enabled

        )





    # =====================================================

    # SAVE

    # =====================================================



    try:



        db.session.commit()





    except SQLAlchemyError:



        db.session.rollback()





        current_app.logger.exception(

            (

                "Unable to update notification "

                "preferences for user %s."

            ),

            current_user.id,

        )





        return jsonify(

            ok=False,

            message=(

                "Unable to save notification preference."

            ),

        ), 500





    return jsonify(



        ok=True,



        email_notifications=(

            bool(

                preferences.email_notifications

            )

        ),



        in_app_alerts=(

            bool(

                preferences.in_app_alerts

            )

        ),

    )





# =========================================================

# PROFILE PHOTO

# =========================================================



@account_bp.route(

    "/profile-photo",

    methods=[

        "POST",

    ],

)

@login_required

def update_profile_photo():

    """

    Save a cropped profile photo for the current user.



    The browser cropper sends a square image using the

    multipart field name ``photo``. The server still

    validates the file independently and normalizes it

    to a 512 x 512 WEBP image before saving.

    """



    photo = request.files.get(

        "photo"

    )



    if (

        photo is None

        or

        not photo.filename

    ):

        return jsonify(

            ok=False,

            message=(

                "No profile photo was provided."

            ),

        ), 400



    # =====================================================

    # FILE SIZE

    # =====================================================



    try:

        photo.stream.seek(

            0,

            2,

        )



        file_size = (

            photo.stream.tell()

        )



        photo.stream.seek(

            0

        )



    except OSError:

        return jsonify(

            ok=False,

            message=(

                "Unable to read the uploaded image."

            ),

        ), 400



    max_size = (

        5

        *

        1024

        *

        1024

    )



    if (

        file_size

        >

        max_size

    ):

        return jsonify(

            ok=False,

            message=(

                "Profile photo must be 5 MB or smaller."

            ),

        ), 400



    # =====================================================

    # VERIFY IMAGE

    # =====================================================



    try:

        image = Image.open(

            photo.stream

        )



        image.verify()



        photo.stream.seek(

            0

        )



        image = Image.open(

            photo.stream

        )



        if (

            image.format

            not in {

                "JPEG",

                "PNG",

                "WEBP",

            }

        ):

            return jsonify(

                ok=False,

                message=(

                    "Only JPG, PNG and WEBP images are allowed."

                ),

            ), 400



        width, height = image.size



        if (

            width <= 0

            or

            height <= 0

            or

            (

                width

                *

                height

            )

            >

            25_000_000

        ):

            return jsonify(

                ok=False,

                message=(

                    "The image dimensions are too large."

                ),

            ), 400



    except (

        UnidentifiedImageError,

        OSError,

        ValueError,

    ):

        return jsonify(

            ok=False,

            message=(

                "The uploaded file is not a valid image."

            ),

        ), 400



    # =====================================================

    # NORMALISE TO SQUARE 512 x 512

    # =====================================================



    image = image.convert(

        "RGB"

    )



    width, height = image.size



    side = min(

        width,

        height,

    )



    left = (

        width

        -

        side

    ) // 2



    top = (

        height

        -

        side

    ) // 2



    image = image.crop(

        (

            left,

            top,

            left + side,

            top + side,

        )

    )



    image = image.resize(

        (

            512,

            512,

        ),

        Image.Resampling.LANCZOS,

    )



    # =====================================================

    # SAVE DIRECTORY

    # =====================================================



    static_folder = Path(

        current_app.static_folder

    )



    profile_directory = (

        static_folder

        /

        "uploads"

        /

        "profiles"

    )



    profile_directory.mkdir(

        parents=True,

        exist_ok=True,

    )



    filename = (

        f"profile_{current_user.id}_"

        f"{uuid4().hex[:12]}.webp"

    )



    output_path = (

        profile_directory

        /

        filename

    )



    # =====================================================

    # WRITE IMAGE

    # =====================================================



    try:

        image.save(

            output_path,

            format="WEBP",

            quality=90,

            method=6,

        )



    except OSError:

        current_app.logger.exception(

            (

                "Unable to write profile photo "

                "for user %s."

            ),

            current_user.id,

        )



        return jsonify(

            ok=False,

            message=(

                "Unable to save profile photo."

            ),

        ), 500



    relative_path = (

        Path(

            "uploads",

            "profiles",

            filename,

        )

        .as_posix()

    )



    previous_photo = (

        current_user.profile_photo

    )



    current_user.profile_photo = (

        relative_path

    )



    # =====================================================

    # DATABASE

    # =====================================================



    try:

        db.session.commit()



    except SQLAlchemyError:

        db.session.rollback()



        try:

            if output_path.exists():

                output_path.unlink()



        except OSError:

            pass



        current_app.logger.exception(

            (

                "Unable to update profile photo "

                "for user %s."

            ),

            current_user.id,

        )



        return jsonify(

            ok=False,

            message=(

                "Unable to save profile photo."

            ),

        ), 500



    # =====================================================

    # DELETE OLD GENERATED PHOTO

    # Supports both the old uploads/profile/ folder and the

    # new uploads/profiles/ folder.

    # =====================================================



    if (

        previous_photo

        and

        previous_photo

        !=

        relative_path

        and

        (

            previous_photo.startswith(

                "uploads/profile/"

            )

            or

            previous_photo.startswith(

                "uploads/profiles/"

            )

        )

    ):

        try:

            previous_path = (

                static_folder

                /

                previous_photo

            )



            if previous_path.is_file():

                previous_path.unlink()



        except OSError:

            current_app.logger.warning(

                (

                    "Unable to remove old profile photo "

                    "for user %s."

                ),

                current_user.id,

            )



    return jsonify(

        ok=True,

        message=(

            "Profile photo updated successfully."

        ),

        photo_url=(

            "/static/"

            +

            relative_path

        ),

    )

