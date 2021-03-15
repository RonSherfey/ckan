from ckan.logic import Context, DataDict, AuthResult

def package_patch(context: Context, data_dict: DataDict) -> AuthResult: ...
def resource_patch(context: Context, data_dict: DataDict) -> AuthResult: ...
def group_patch(context: Context, data_dict: DataDict) -> AuthResult: ...
def organization_patch(
    context: Context, data_dict: DataDict
) -> AuthResult: ...
def user_patch(context: Context, data_dict: DataDict) -> AuthResult: ...
