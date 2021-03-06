from flask_login import current_user
from flask import render_template, request, redirect, url_for, abort, flash, current_app

from ... import data_api_client, flask_featureflags
from ...main import main, content_loader
from ..helpers import login_required
from ..helpers.services import is_service_associated_with_supplier, get_signed_document_url, count_unanswered_questions
from ..helpers.frameworks import (
    get_framework_and_lot,
    get_declaration_status,
    get_supplier_framework_info,
    get_framework,
)

from dmcontent.content_loader import ContentNotFoundError
from dmapiclient import HTTPError
from dmutils import s3
from dmutils.documents import upload_service_documents


@main.route("/frameworks/<string:framework_slug>/services")
@login_required
def list_services(framework_slug):
    framework = get_framework(data_api_client, framework_slug, allowed_statuses=['live'])

    suppliers_services = data_api_client.find_services(
        supplier_id=current_user.supplier_id,
        framework=framework_slug,
    )["services"]

    return render_template(
        "services/list_services.html",
        services=suppliers_services,
        framework=framework,
    ), 200


#  #######################  EDITING LIVE SERVICES #############################


@main.route("/frameworks/<string:framework_slug>/services/<string:service_id>", methods=['GET'])
@login_required
def edit_service(framework_slug, service_id):
    service = data_api_client.get_service(service_id)
    service_unavailability_information = service.get('serviceMadeUnavailableAuditEvent')
    service = service.get('services')

    if not is_service_associated_with_supplier(service):
        abort(404)

    if service["frameworkSlug"] != framework_slug:
        abort(404)

    framework = data_api_client.get_framework(service['frameworkSlug'])['frameworks']

    try:
        content = content_loader.get_manifest(framework['slug'], 'edit_service').filter(service)
    except ContentNotFoundError:
        abort(404)
    remove_requested = bool(request.args.get('remove_requested'))

    return render_template(
        "services/service.html",
        service_id=service.get('id'),
        service_data=service,
        service_unavailability_information=service_unavailability_information,
        framework=framework,
        sections=content.summary(service),
        remove_requested=remove_requested,
    )


@main.route("/frameworks/<string:framework_slug>/services/<string:service_id>/remove", methods=['POST'])
@login_required
def remove_service(framework_slug, service_id):
    service = data_api_client.get_service(service_id).get('services')

    if not is_service_associated_with_supplier(service):
        abort(404)

    if service["frameworkSlug"] != framework_slug:
        abort(404)

    # dos services should not be removable
    if service["frameworkFramework"] == 'digital-outcomes-and-specialists':
        abort(404)

    # we don't actually need the content here, we're just probing to see whether service editing should be allowed for
    # this framework (signalled by the existence of the edit_service manifest
    try:
        content_loader.get_manifest(service["frameworkSlug"], 'edit_service')
    except ContentNotFoundError:
        abort(404)

    # suppliers can't un-remove a service
    if service.get('status') != 'published':
        abort(400)

    if request.form.get('remove_confirmed'):

        updated_service = data_api_client.update_service_status(
            service.get('id'),
            'enabled',
            current_user.email_address)

        updated_service = updated_service.get('services')

        flash({
            'updated_service_name': updated_service.get('serviceName')
        }, 'remove_service')

        return redirect(url_for(".list_services", framework_slug=service["frameworkSlug"]))

    return redirect(url_for(
        ".edit_service",
        service_id=service_id,
        framework_slug=service["frameworkSlug"],
        remove_requested=True))


@main.route(
    "/frameworks/<string:framework_slug>/services/<string:service_id>/edit/<string:section_id>",
    methods=['GET'],
)
@login_required
@flask_featureflags.is_active_feature('EDIT_SECTIONS')
def edit_section(framework_slug, service_id, section_id):
    service = data_api_client.get_service(service_id)
    if service is None:
        abort(404)
    service = service['services']

    if not is_service_associated_with_supplier(service):
        abort(404)

    if service["frameworkSlug"] != framework_slug:
        abort(404)

    try:
        content = content_loader.get_manifest(service["frameworkSlug"], 'edit_service').filter(service)
    except ContentNotFoundError:
        abort(404)
    section = content.get_section(section_id)
    if section is None or not section.editable:
        abort(404)

    return render_template(
        "services/edit_section.html",
        section=section,
        service_data=service,
        service_id=service_id,
    )


@main.route(
    "/frameworks/<string:framework_slug>/services/<string:service_id>/edit/<string:section_id>",
    methods=['POST'],
)
@login_required
@flask_featureflags.is_active_feature('EDIT_SECTIONS')
def update_section(framework_slug, service_id, section_id):
    service = data_api_client.get_service(service_id)
    if service is None:
        abort(404)
    service = service['services']

    if not is_service_associated_with_supplier(service):
        abort(404)

    if service["frameworkSlug"] != framework_slug:
        abort(404)

    try:
        content = content_loader.get_manifest(service["frameworkSlug"], 'edit_service').filter(service)
    except ContentNotFoundError:
        abort(404)
    section = content.get_section(section_id)
    if section is None or not section.editable:
        abort(404)

    posted_data = section.get_data(request.form)

    try:
        data_api_client.update_service(
            service_id,
            posted_data,
            current_user.email_address)
    except HTTPError as e:
        errors = section.get_error_messages(e.message)
        if not posted_data.get('serviceName', None):
            posted_data['serviceName'] = service.get('serviceName', '')
        return render_template(
            "services/edit_section.html",
            section=section,
            service_data=posted_data,
            service_id=service_id,
            errors=errors,
        )

    flash({"updated_service_name": posted_data.get("serviceName") or service.get("serviceName")}, 'service_updated')

    return redirect(url_for(".edit_service", service_id=service_id, framework_slug=service["frameworkSlug"]))


# we have to split these route definitions in two because without a fixed "/" separating the service_id and
# trailing_path it's not clearly defined where flask should start capturing trailing_path
@main.route("/services/<string:service_id>", defaults={"trailing_path": ""})
@main.route("/services/<string:service_id>/<path:trailing_path>")
@login_required
def redirect_direct_service_urls(service_id, trailing_path):
    service_response = data_api_client.get_service(service_id)
    if service_response is None:
        abort(404)
    service = service_response["services"]

    # technically we could rely on the target view to do the access restriction, but this would still allow a
    # user from a different supplier to sniff the existence & framework of a service id
    if not is_service_associated_with_supplier(service):
        abort(404)

    # note this relies on the views beneath /services/<service_id>/... remaining beneath
    # /frameworks/<framework_slug>/services/<service_id>/..., but allows us to build one redirector to work for a number
    # of views
    return redirect(url_for(
        ".edit_service",
        framework_slug=service["frameworkSlug"],
        service_id=service_id,
    ) + (trailing_path and ("/" + trailing_path)))


#  ####################  CREATING NEW DRAFT SERVICES ##########################


@main.route('/frameworks/<framework_slug>/submissions/<lot_slug>/create', methods=['GET', 'POST'])
@login_required
def start_new_draft_service(framework_slug, lot_slug):
    """Page to kick off creation of a new service."""

    framework, lot = get_framework_and_lot(data_api_client, framework_slug, lot_slug, allowed_statuses=['open'])

    # Suppliers must have registered interest in a framework before they can create draft services
    if not get_supplier_framework_info(data_api_client, framework_slug):
        abort(404)

    content = content_loader.get_manifest(framework_slug, 'edit_submission').filter(
        {'lot': lot['slug']}
    )

    section = content.get_section(content.get_next_editable_section_id())
    if section is None:
        section = content.get_section(content.get_next_edit_questions_section_id(None))
        if section is None:
            abort(404)

        section = section.get_question_as_section(section.get_next_question_slug())

    if request.method == 'POST':
        update_data = section.get_data(request.form)

        try:
            draft_service = data_api_client.create_new_draft_service(
                framework_slug, lot['slug'], current_user.supplier_id, update_data,
                current_user.email_address, page_questions=section.get_field_names()
            )['services']
        except HTTPError as e:
            update_data = section.unformat_data(update_data)
            errors = section.get_error_messages(e.message)

            return render_template(
                "services/edit_submission_section.html",
                framework=framework,
                section=section,
                service_data=update_data,
                errors=errors
            ), 400

        return redirect(
            url_for(
                ".view_service_submission",
                framework_slug=framework['slug'],
                lot_slug=draft_service['lotSlug'],
                service_id=draft_service['id'],
            )
        )

    return render_template(
        "services/edit_submission_section.html",
        framework=framework,
        lot=lot,
        service_data={},
        section=section,
        force_continue_button=True,
    ), 200


@main.route('/frameworks/<framework_slug>/submissions/<lot_slug>/<service_id>/copy', methods=['POST'])
@login_required
def copy_draft_service(framework_slug, lot_slug, service_id):
    framework, lot = get_framework_and_lot(data_api_client, framework_slug, lot_slug, allowed_statuses=['open'])

    # Suppliers must have registered interest in a framework before they can edit draft services
    if not get_supplier_framework_info(data_api_client, framework_slug):
        abort(404)

    draft = data_api_client.get_draft_service(service_id).get('services')

    if draft['lotSlug'] != lot_slug or draft['frameworkSlug'] != framework_slug:
        abort(404)

    if not is_service_associated_with_supplier(draft):
        abort(404)

    content = content_loader.get_manifest(framework_slug, 'edit_submission').filter(
        {'lot': lot['slug']}
    )

    draft_copy = data_api_client.copy_draft_service(
        service_id,
        current_user.email_address
    )['services']

    # Get the first section or question to edit.
    section_id_to_edit = content.get_next_editable_section_id()
    if section_id_to_edit is None:
        section_id_to_edit = content.get_next_edit_questions_section_id()
        question_slug_to_edit = content.get_section(section_id_to_edit).get_next_question_slug()
        if question_slug_to_edit is None:
            abort(404)
    else:
        question_slug_to_edit = None

    return redirect(url_for(".edit_service_submission",
                            framework_slug=framework['slug'],
                            lot_slug=draft['lotSlug'],
                            service_id=draft_copy['id'],
                            section_id=section_id_to_edit,
                            question_slug=question_slug_to_edit,
                            return_to_summary=1
                            ))


@main.route('/frameworks/<framework_slug>/submissions/<lot_slug>/<service_id>/complete', methods=['POST'])
@login_required
def complete_draft_service(framework_slug, lot_slug, service_id):
    framework, lot = get_framework_and_lot(data_api_client, framework_slug, lot_slug, allowed_statuses=['open'])

    # Suppliers must have registered interest in a framework before they can complete draft services
    if not get_supplier_framework_info(data_api_client, framework_slug):
        abort(404)

    draft = data_api_client.get_draft_service(service_id).get('services')

    if draft['lotSlug'] != lot_slug or draft['frameworkSlug'] != framework_slug:
        abort(404)

    if not is_service_associated_with_supplier(draft):
        abort(404)

    data_api_client.complete_draft_service(
        service_id,
        current_user.email_address
    )

    flash({
        'service_name': draft.get('serviceName') or draft.get('lotName'),
        'virtual_pageview_url': "{}/{}/{}".format(
            url_for(".framework_submission_lots", framework_slug=framework['slug']),
            lot_slug,
            "complete"
        )
    }, 'service_completed')

    if lot['oneServiceLimit']:
        return redirect(url_for(".framework_submission_lots", framework_slug=framework['slug']))
    else:
        return redirect(url_for(".framework_submission_services",
                                framework_slug=framework['slug'],
                                lot_slug=lot_slug,
                                lot=lot_slug))


@main.route('/frameworks/<framework_slug>/submissions/<lot_slug>/<service_id>/delete', methods=['POST'])
@login_required
def delete_draft_service(framework_slug, lot_slug, service_id):
    framework, lot = get_framework_and_lot(data_api_client, framework_slug, lot_slug, allowed_statuses=['open'])

    # Suppliers must have registered interest in a framework before they can delete draft services
    if not get_supplier_framework_info(data_api_client, framework_slug):
        abort(404)

    draft = data_api_client.get_draft_service(service_id).get('services')

    if draft['lotSlug'] != lot_slug or draft['frameworkSlug'] != framework_slug:
        abort(404)

    if not is_service_associated_with_supplier(draft):
        abort(404)

    if request.form.get('delete_confirmed') == 'true':
        data_api_client.delete_draft_service(
            service_id,
            current_user.email_address
        )

        flash({'service_name': draft.get('serviceName', draft['lotName'])}, 'service_deleted')
        if lot['oneServiceLimit']:
            return redirect(url_for(".framework_submission_lots", framework_slug=framework['slug']))
        else:
            return redirect(url_for(".framework_submission_services",
                                    framework_slug=framework['slug'],
                                    lot_slug=lot_slug))
    else:
        return redirect(url_for(".view_service_submission",
                                framework_slug=framework['slug'],
                                lot_slug=draft['lotSlug'],
                                service_id=service_id,
                                delete_requested=True))


@main.route('/assets/<framework_slug>/submissions/<int:supplier_id>/<document_name>', methods=['GET'])
@login_required
def service_submission_document(framework_slug, supplier_id, document_name):
    if current_user.supplier_id != supplier_id:
        abort(404)

    uploader = s3.S3(current_app.config['DM_SUBMISSIONS_BUCKET'])
    s3_url = get_signed_document_url(uploader,
                                     "{}/submissions/{}/{}".format(framework_slug, supplier_id, document_name))
    if not s3_url:
        abort(404)

    return redirect(s3_url)


@main.route('/frameworks/<framework_slug>/submissions/<lot_slug>/<service_id>', methods=['GET'])
@login_required
def view_service_submission(framework_slug, lot_slug, service_id):
    framework, lot = get_framework_and_lot(data_api_client, framework_slug, lot_slug)

    try:
        data = data_api_client.get_draft_service(service_id)
        draft, last_edit, validation_errors = data['services'], data['auditEvents'], data['validationErrors']
    except HTTPError as e:
        abort(e.status_code)

    if draft['lotSlug'] != lot_slug or draft['frameworkSlug'] != framework_slug:
        abort(404)

    if not is_service_associated_with_supplier(draft):
        abort(404)

    content = content_loader.get_manifest(framework['slug'], 'edit_submission').filter(draft)

    sections = content.summary(draft)

    unanswered_required, unanswered_optional = count_unanswered_questions(sections)
    delete_requested = True if request.args.get('delete_requested') else False

    return render_template(
        "services/service_submission.html",
        framework=framework,
        lot=lot,
        confirm_remove=request.args.get("confirm_remove", None),
        service_id=service_id,
        service_data=draft,
        last_edit=last_edit,
        sections=sections,
        unanswered_required=unanswered_required,
        unanswered_optional=unanswered_optional,
        can_mark_complete=not validation_errors,
        delete_requested=delete_requested,
        declaration_status=get_declaration_status(data_api_client, framework['slug']),
        dates=content_loader.get_message(framework_slug, 'dates')
    ), 200


@main.route('/frameworks/<framework_slug>/submissions/<lot_slug>/<service_id>/edit/<section_id>',
            methods=('GET', 'POST',))
@main.route('/frameworks/<framework_slug>/submissions/<lot_slug>/<service_id>/edit/<section_id>/<question_slug>',
            methods=('GET', 'POST',))
@login_required
def edit_service_submission(framework_slug, lot_slug, service_id, section_id, question_slug=None):
    """
        Also accepts URL parameter `return_to_summary` which will remove the ability to continue to the next section
        on submit
    """
    framework, lot = get_framework_and_lot(data_api_client, framework_slug, lot_slug, allowed_statuses=['open'])

    # Suppliers must have registered interest in a framework before they can edit draft services
    if not get_supplier_framework_info(data_api_client, framework_slug):
        abort(404)

    force_return_to_summary = (
        request.args.get('return_to_summary') or framework['framework'] == "digital-outcomes-and-specialists"
    )
    next_question = None

    try:
        draft = data_api_client.get_draft_service(service_id)['services']
    except HTTPError as e:
        abort(e.status_code)

    if draft['lotSlug'] != lot_slug or draft['frameworkSlug'] != framework_slug:
        abort(404)

    if not is_service_associated_with_supplier(draft):
        abort(404)

    content = content_loader.get_manifest(framework_slug, 'edit_submission').filter(draft)
    section = content.get_section(section_id)
    if section and (question_slug is not None):
        next_question = section.get_question_by_slug(section.get_next_question_slug(question_slug))
        section = section.get_question_as_section(question_slug)

    if section is None or not section.editable:
        abort(404)

    errors = None
    if request.method == "POST":
        update_data = section.get_data(request.form)

        if request.files:
            uploader = s3.S3(current_app.config['DM_SUBMISSIONS_BUCKET'])
            documents_url = url_for('.dashboard', _external=True) + '/assets/'
            uploaded_documents, document_errors = upload_service_documents(
                uploader, 'submissions', documents_url, draft, request.files, section,
                public=False)

            if document_errors:
                errors = section.get_error_messages(document_errors, question_descriptor_from="question")
            else:
                update_data.update(uploaded_documents)

        if not errors and section.has_changes_to_save(draft, update_data):
            try:
                data_api_client.update_draft_service(
                    service_id,
                    update_data,
                    current_user.email_address,
                    page_questions=section.get_field_names()
                )
            except HTTPError as e:
                update_data = section.unformat_data(update_data)
                errors = section.get_error_messages(e.message, question_descriptor_from="question")

        if not errors:
            if next_question and not force_return_to_summary:
                return redirect(url_for(".edit_service_submission",
                                        framework_slug=framework['slug'],
                                        lot_slug=draft['lotSlug'],
                                        service_id=service_id,
                                        section_id=section_id,
                                        question_slug=next_question.slug))
            else:
                return redirect(url_for(".view_service_submission",
                                        framework_slug=framework['slug'],
                                        lot_slug=draft['lotSlug'],
                                        service_id=service_id,
                                        _anchor=section_id))

        update_data.update(
            (k, draft[k]) for k in ('serviceName', 'lot', 'lotName',) if k in draft and k not in update_data
        )
        service_data = update_data
        # fall through to regular GET path to display errors
    else:
        service_data = section.unformat_data(draft)

    return render_template(
        "services/edit_submission_section.html",
        section=section,
        framework=framework,
        lot=lot,
        next_question=next_question,
        service_data=service_data,
        service_id=service_id,
        force_return_to_summary=force_return_to_summary,
        errors=errors,
    )


@main.route('/frameworks/<framework_slug>/submissions/<lot_slug>/<service_id>/remove/<section_id>/<question_slug>',
            methods=['GET', 'POST'])
@login_required
def remove_subsection(framework_slug, lot_slug, service_id, section_id, question_slug):
    # Suppliers must have registered interest in a framework before they can edit draft services
    if not get_supplier_framework_info(data_api_client, framework_slug):
        abort(404)

    try:
        draft = data_api_client.get_draft_service(service_id)['services']
    except HTTPError as e:
        abort(e.status_code)

    if not is_service_associated_with_supplier(draft):
        abort(404)

    content = content_loader.get_manifest(framework_slug, 'edit_submission').filter(draft)
    section = content.get_section(section_id)
    containing_section = section
    if section and (question_slug is not None):
        section = section.get_question_as_section(question_slug)
    if section is None or not section.editable:
        abort(404)

    question_to_remove = content.get_question_by_slug(question_slug)
    fields_to_remove = question_to_remove.form_fields

    if request.args.get("confirm") and request.method == "POST":
        # Remove the section
        update_json = {field: None for field in fields_to_remove}
        try:
            data_api_client.update_draft_service(
                service_id,
                update_json,
                current_user.email_address
            )
            flash({'service_name': question_to_remove.label}, 'service_deleted')
        except HTTPError as e:
            if e.status_code == 400:
                # You can't remove the last one
                flash({
                    'remove_last_attempted': containing_section.name,
                    'service_name': question_to_remove.label
                }, 'error')
            else:
                abort(e.status_code)

    else:
        section_responses = [field for field in containing_section.get_field_names() if field in draft]
        fields_remaining_after_removal = [field for field in section_responses if field not in fields_to_remove]

        if draft['status'] == 'not-submitted' or len(fields_remaining_after_removal) > 0:
            # Show page with "Are you sure?" message and button
            return redirect(
                url_for('.view_service_submission',
                        framework_slug=framework_slug,
                        lot_slug=lot_slug,
                        service_id=service_id,
                        confirm_remove=question_slug,
                        section_id=section_id
                        )
            )
        else:
            # You can't remove the last one
            flash({
                'remove_last_attempted': containing_section.name,
                'service_name': question_to_remove.label,
                'virtual_pageview_url': "{}/{}".format(
                    url_for(".remove_subsection",
                            framework_slug=framework_slug,
                            lot_slug=lot_slug,
                            service_id=service_id,
                            section_id=section_id,
                            question_slug=question_slug
                            ),
                    "remove-last-subsection-attempt"
                )
            }, 'error')

    return redirect(
        url_for('.view_service_submission',
                framework_slug=framework_slug,
                lot_slug=lot_slug,
                service_id=service_id,
                confirm_remove=None
                ))
