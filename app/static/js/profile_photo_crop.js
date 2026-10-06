/* =========================================================
   BIKA PROFILE PHOTO CROPPER
   ========================================================= */

(() => {

    "use strict";


    const photoButton =
        document.getElementById(
            "profilePhotoButton"
        );


    const photoInput =
        document.getElementById(
            "profilePhotoInput"
        );


    const backdrop =
        document.getElementById(
            "profileCropBackdrop"
        );


    const viewport =
        document.getElementById(
            "profileCropViewport"
        );


    const image =
        document.getElementById(
            "profileCropImage"
        );


    const zoomInput =
        document.getElementById(
            "profileCropZoom"
        );


    const closeButton =
        document.getElementById(
            "profileCropClose"
        );


    const cancelButton =
        document.getElementById(
            "profileCropCancel"
        );


    const saveButton =
        document.getElementById(
            "profileCropSave"
        );


    if (
        !photoButton
        ||
        !photoInput
        ||
        !backdrop
        ||
        !viewport
        ||
        !image
        ||
        !zoomInput
        ||
        !closeButton
        ||
        !cancelButton
        ||
        !saveButton
    ) {
        return;
    }


    /* =====================================================
       STATE
       ===================================================== */

    let objectUrl = null;

    let naturalWidth = 0;
    let naturalHeight = 0;

    let baseScale = 1;
    let scale = 1;

    let positionX = 0;
    let positionY = 0;

    let dragging = false;

    let dragStartX = 0;
    let dragStartY = 0;

    let positionStartX = 0;
    let positionStartY = 0;


    const MAX_FILE_SIZE =
        5 * 1024 * 1024;


    /* =====================================================
       CSRF
       ===================================================== */

    function csrfToken() {

        const meta =
            document.querySelector(
                'meta[name="csrf-token"]'
            );

        return (
            meta
                ? meta.content
                : ""
        );

    }


    /* =====================================================
       VIEWPORT SIZE
       ===================================================== */

    function viewportSize() {

        return viewport
            .getBoundingClientRect()
            .width;

    }


    /* =====================================================
       CLAMP POSITION
       Prevent blank areas from showing
       ===================================================== */

    function clampPosition() {

        const size =
            viewportSize();


        const imageWidth =
            naturalWidth
            *
            scale;


        const imageHeight =
            naturalHeight
            *
            scale;


        const minX =
            size
            -
            imageWidth;


        const minY =
            size
            -
            imageHeight;


        positionX =
            Math.min(
                0,
                Math.max(
                    minX,
                    positionX
                )
            );


        positionY =
            Math.min(
                0,
                Math.max(
                    minY,
                    positionY
                )
            );

    }


    /* =====================================================
       RENDER
       ===================================================== */

    function render() {

        if (
            !naturalWidth
            ||
            !naturalHeight
        ) {
            return;
        }


        clampPosition();


        image.style.width =
            `${naturalWidth * scale}px`;


        image.style.height =
            `${naturalHeight * scale}px`;


        image.style.transform =
            `translate(
                ${positionX}px,
                ${positionY}px
            )`;

    }


    /* =====================================================
       CENTER IMAGE
       ===================================================== */

    function centerImage() {

        const size =
            viewportSize();


        positionX =
            (
                size
                -
                naturalWidth
                *
                scale
            )
            /
            2;


        positionY =
            (
                size
                -
                naturalHeight
                *
                scale
            )
            /
            2;


        render();

    }


    /* =====================================================
       OPEN MODAL
       ===================================================== */

    function openModal() {

        backdrop.hidden = false;

        document.body.style.overflow =
            "hidden";

    }


    /* =====================================================
       CLOSE MODAL
       ===================================================== */

    function closeModal() {

        backdrop.hidden = true;

        document.body.style.overflow =
            "";

        dragging = false;

        viewport.classList.remove(
            "is-dragging"
        );


        photoInput.value = "";


        if (objectUrl) {

            URL.revokeObjectURL(
                objectUrl
            );

            objectUrl = null;

        }

    }


    /* =====================================================
       OPEN FILE PICKER
       ===================================================== */

    photoButton.addEventListener(
        "click",
        () => {

            photoInput.click();

        }
    );


    /* =====================================================
       FILE SELECTED
       ===================================================== */

    photoInput.addEventListener(
        "change",
        () => {

            const file =
                photoInput.files
                    &&
                photoInput.files[0];


            if (!file) {
                return;
            }


            const allowedTypes = [
                "image/jpeg",
                "image/png",
                "image/webp"
            ];


            if (
                !allowedTypes.includes(
                    file.type
                )
            ) {

                alert(
                    "Please select a JPG, PNG or WEBP image."
                );

                photoInput.value = "";

                return;

            }


            if (
                file.size
                >
                MAX_FILE_SIZE
            ) {

                alert(
                    "Profile photo must be 5 MB or smaller."
                );

                photoInput.value = "";

                return;

            }


            if (objectUrl) {

                URL.revokeObjectURL(
                    objectUrl
                );

            }


            objectUrl =
                URL.createObjectURL(
                    file
                );


            image.onload = () => {

                naturalWidth =
                    image.naturalWidth;


                naturalHeight =
                    image.naturalHeight;


                openModal();


                requestAnimationFrame(
                    () => {

                        const size =
                            viewportSize();


                        baseScale =
                            Math.max(
                                size
                                /
                                naturalWidth,

                                size
                                /
                                naturalHeight
                            );


                        scale =
                            baseScale;


                        zoomInput.value =
                            "100";


                        centerImage();

                    }
                );

            };


            image.src =
                objectUrl;

        }
    );


    /* =====================================================
       ZOOM
       ===================================================== */

    zoomInput.addEventListener(
        "input",
        () => {

            if (
                !naturalWidth
                ||
                !naturalHeight
            ) {
                return;
            }


            const size =
                viewportSize();


            /*
             * Keep the crop centre fixed while zooming.
             */

            const oldScale =
                scale;


            const centerSourceX =
                (
                    size / 2
                    -
                    positionX
                )
                /
                oldScale;


            const centerSourceY =
                (
                    size / 2
                    -
                    positionY
                )
                /
                oldScale;


            const zoom =
                Number(
                    zoomInput.value
                )
                /
                100;


            scale =
                baseScale
                *
                zoom;


            positionX =
                size / 2
                -
                centerSourceX
                *
                scale;


            positionY =
                size / 2
                -
                centerSourceY
                *
                scale;


            render();

        }
    );


    /* =====================================================
       POINTER DRAG
       ===================================================== */

    viewport.addEventListener(
        "pointerdown",
        (event) => {

            if (
                !naturalWidth
                ||
                !naturalHeight
            ) {
                return;
            }


            dragging = true;


            dragStartX =
                event.clientX;


            dragStartY =
                event.clientY;


            positionStartX =
                positionX;


            positionStartY =
                positionY;


            viewport.classList.add(
                "is-dragging"
            );


            viewport.setPointerCapture(
                event.pointerId
            );

        }
    );


    viewport.addEventListener(
        "pointermove",
        (event) => {

            if (!dragging) {
                return;
            }


            positionX =
                positionStartX
                +
                (
                    event.clientX
                    -
                    dragStartX
                );


            positionY =
                positionStartY
                +
                (
                    event.clientY
                    -
                    dragStartY
                );


            render();

        }
    );


    function stopDragging(
        event
    ) {

        if (!dragging) {
            return;
        }


        dragging = false;


        viewport.classList.remove(
            "is-dragging"
        );


        if (
            event
            &&
            viewport.hasPointerCapture(
                event.pointerId
            )
        ) {

            viewport.releasePointerCapture(
                event.pointerId
            );

        }

    }


    viewport.addEventListener(
        "pointerup",
        stopDragging
    );


    viewport.addEventListener(
        "pointercancel",
        stopDragging
    );


    /* =====================================================
       SAVE CROP
       ===================================================== */

    saveButton.addEventListener(
        "click",
        async () => {

            if (
                !naturalWidth
                ||
                !naturalHeight
            ) {
                return;
            }


            saveButton.disabled = true;

            const oldText =
                saveButton.textContent;


            saveButton.textContent =
                "Saving...";


            try {

                const size =
                    viewportSize();


                /*
                 * Convert screen crop position
                 * back into original-image coordinates.
                 */

                const sourceX =
                    Math.max(
                        0,
                        -positionX
                        /
                        scale
                    );


                const sourceY =
                    Math.max(
                        0,
                        -positionY
                        /
                        scale
                    );


                const sourceSize =
                    size
                    /
                    scale;


                const canvas =
                    document.createElement(
                        "canvas"
                    );


                canvas.width =
                    512;


                canvas.height =
                    512;


                const context =
                    canvas.getContext(
                        "2d",
                        {
                            alpha: false
                        }
                    );


                context.imageSmoothingEnabled =
                    true;


                context.imageSmoothingQuality =
                    "high";


                context.drawImage(
                    image,

                    sourceX,
                    sourceY,
                    sourceSize,
                    sourceSize,

                    0,
                    0,
                    512,
                    512
                );


                const blob =
                    await new Promise(
                        (
                            resolve,
                            reject
                        ) => {

                            canvas.toBlob(
                                (result) => {

                                    if (result) {

                                        resolve(
                                            result
                                        );

                                    }
                                    else {

                                        reject(
                                            new Error(
                                                "Unable to create cropped image."
                                            )
                                        );

                                    }

                                },
                                "image/webp",
                                0.90
                            );

                        }
                    );


                const formData =
                    new FormData();


                formData.append(
                    "photo",
                    blob,
                    "profile.webp"
                );


                const response =
                    await fetch(
                        "/account/profile-photo",
                        {
                            method: "POST",

                            headers: {
                                "X-CSRFToken":
                                    csrfToken()
                            },

                            body:
                                formData
                        }
                    );


                const result =
                    await response.json();


                if (
                    !response.ok
                    ||
                    !result.ok
                ) {

                    throw new Error(
                        result.message
                        ||
                        "Unable to save profile photo."
                    );

                }


                closeModal();


                /*
                 * Reload so:
                 * - Account avatar
                 * - Sidebar avatar
                 * - any other current-user avatar
                 * all refresh together.
                 */

                window.location.reload();

            }
            catch (error) {

                alert(
                    error.message
                    ||
                    "Unable to save profile photo."
                );

            }
            finally {

                saveButton.disabled = false;

                saveButton.textContent =
                    oldText;

            }

        }
    );


    /* =====================================================
       CLOSE ACTIONS
       ===================================================== */

    closeButton.addEventListener(
        "click",
        closeModal
    );


    cancelButton.addEventListener(
        "click",
        closeModal
    );


    backdrop.addEventListener(
        "click",
        (event) => {

            if (
                event.target
                ===
                backdrop
            ) {

                closeModal();

            }

        }
    );


    document.addEventListener(
        "keydown",
        (event) => {

            if (
                event.key
                ===
                "Escape"
                &&
                !backdrop.hidden
            ) {

                closeModal();

            }

        }
    );

})();