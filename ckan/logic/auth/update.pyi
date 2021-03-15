from ckan.logic import Context, DataDict, AuthResult

def package_update(context: Context, data_dict: DataDict) -> AuthResult: ...
def package_revise(context: Context, data_dict: DataDict) -> AuthResult: ...
def package_resource_reorder(
    context: Context, data_dict: DataDict
) -> AuthResult: ...
def resource_update(context: Context, data_dict: DataDict) -> AuthResult: ...
def resource_view_update(
    context: Context, data_dict: DataDict
) -> AuthResult: ...
def resource_view_reorder(
    context: Context, data_dict: DataDict
) -> AuthResult: ...
def package_relationship_update(
    context: Context, data_dict: DataDict
) -> AuthResult: ...
def package_change_state(
    context: Context, data_dict: DataDict
) -> AuthResult: ...
def group_update(context: Context, data_dict: DataDict) -> AuthResult: ...
def organization_update(
    context: Context, data_dict: DataDict
) -> AuthResult: ...
def group_change_state(
    context: Context, data_dict: DataDict
) -> AuthResult: ...
def group_edit_permissions(
    context: Context, data_dict: DataDict
) -> AuthResult: ...
def user_update(context: Context, data_dict: DataDict) -> AuthResult: ...
def user_generate_apikey(
    context: Context, data_dict: DataDict
) -> AuthResult: ...
def revision_change_state(
    context: Context, data_dict: DataDict
) -> AuthResult: ...
def task_status_update(
    context: Context, data_dict: DataDict
) -> AuthResult: ...
def vocabulary_update(context: Context, data_dict: DataDict) -> AuthResult: ...
def term_translation_update(
    context: Context, data_dict: DataDict
) -> AuthResult: ...
def dashboard_mark_activities_old(
    context: Context, data_dict: DataDict
) -> AuthResult: ...
def send_email_notifications(
    context: Context, data_dict: DataDict
) -> AuthResult: ...
def package_owner_org_update(
    context: Context, data_dict: DataDict
) -> AuthResult: ...
def bulk_update_private(
    context: Context, data_dict: DataDict
) -> AuthResult: ...
def bulk_update_public(
    context: Context, data_dict: DataDict
) -> AuthResult: ...
def bulk_update_delete(
    context: Context, data_dict: DataDict
) -> AuthResult: ...
def config_option_update(
    context: Context, data_dict: DataDict
) -> AuthResult: ...
