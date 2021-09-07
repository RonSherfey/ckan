# encoding: utf-8
"""Unit tests for ckan/logic/auth/update.py.

"""
import unittest.mock as mock
import pytest


import ckan.logic as logic
import ckan.model as model
import ckan.tests.helpers as helpers


@pytest.mark.usefixtures("with_request_context")
def test_user_update_visitor_cannot_update_user(mock_user_factory):
    """Visitors should not be able to update users' accounts."""

    # Make a mock ckan.model.User object, Fred.
    fred = mock_user_factory(name="fred")

    # Make a mock ckan.model object.
    mock_model = mock.MagicMock()
    # model.User.get(user_id) should return Fred.
    mock_model.User.get.return_value = fred

    # Put the mock model in the context.
    # This is easier than patching import ckan.model.
    context = {"model": mock_model}

    # No user is going to be logged-in.
    context["user"] = "127.0.0.1"

    # Make the visitor try to update Fred's user account.
    params = {"id": fred.id, "name": "updated_user_name"}

    with pytest.raises(logic.NotAuthorized):
        helpers.call_auth("user_update", context=context, **params)


# START-AFTER


@pytest.mark.usefixtures("with_request_context")
def test_user_update_user_cannot_update_another_user(mock_user_factory):
    """Users should not be able to update other users' accounts."""

    # 1. Setup.

    # Make a mock ckan.model.User object, Fred.
    fred = mock_user_factory(name="fred")

    # Make a mock ckan.model object.
    mock_model = mock.MagicMock()
    # model.User.get(user_id) should return Fred.
    mock_model.User.get.return_value = fred

    # Put the mock model in the context.
    # This is easier than patching import ckan.model.
    context = {"model": mock_model}

    # The logged-in user is going to be Bob, not Fred.
    context["user"] = "bob"

    # 2. Call the function that's being tested, once only.

    # Make Bob try to update Fred's user account.
    params = {"id": fred.id, "name": "updated_user_name"}

    # 3. Make assertions about the return value and/or side-effects.

    with pytest.raises(logic.NotAuthorized):
        helpers.call_auth("user_update", context=context, **params)

    # 4. Do nothing else!


# END-BEFORE


@pytest.mark.usefixtures("with_request_context")
def test_user_update_user_can_update_her(mock_user_factory):
    """Users should be authorized to update their own accounts."""

    # Make a mock ckan.model.User object, Fred.
    fred = mock_user_factory(name="fred")

    # Make a mock ckan.model object.
    mock_model = mock.MagicMock()
    # model.User.get(user_id) should return our mock user.
    mock_model.User.get.return_value = fred

    # Put the mock model in the context.
    # This is easier than patching import ckan.model.
    context = {"model": mock_model}

    # The 'user' in the context has to match fred.name, so that the
    # auth function thinks that the user being updated is the same user as
    # the user who is logged-in.
    context["user"] = fred.name

    # Make Fred try to update his own user name.
    params = {"id": fred.id, "name": "updated_user_name"}

    result = helpers.call_auth("user_update", context=context, **params)
    assert result is True


def test_user_update_with_no_user_in_context(mock_user_factory):

    # Make a mock ckan.model.User object.
    mock_user = mock_user_factory(name="fred")

    # Make a mock ckan.model object.
    mock_model = mock.MagicMock()
    # model.User.get(user_id) should return our mock user.
    mock_model.User.get.return_value = mock_user

    # Put the mock model in the context.
    # This is easier than patching import ckan.model.
    context = {"model": mock_model}

    # For this test we're going to have no 'user' in the context.
    context["user"] = None

    params = {"id": mock_user.id, "name": "updated_user_name"}

    with pytest.raises(logic.NotAuthorized):
        helpers.call_auth("user_update", context=context, **params)


@pytest.mark.usefixtures("with_request_context")
def test_user_generate_own_apikey(mock_user_factory):
    fred = mock_user_factory(name="fred")
    mock_model = mock.MagicMock()
    mock_model.User.get.return_value = fred
    # auth_user_obj shows user as logged in for non-anonymous auth
    # functions
    context = {"model": mock_model, "auth_user_obj": fred}
    context["user"] = fred.name
    params = {"id": fred.id}

    result = helpers.call_auth(
        "user_generate_apikey", context=context, **params
    )
    assert result is True


@pytest.mark.usefixtures("with_request_context")
def test_user_generate_apikey_without_logged_in_user(mock_user_factory):
    fred = mock_user_factory(name="fred")
    mock_model = mock.MagicMock()
    mock_model.User.get.return_value = fred
    context = {"model": mock_model}
    context["user"] = None
    params = {"id": fred.id}

    with pytest.raises(logic.NotAuthorized):
        helpers.call_auth("user_generate_apikey", context=context, **params)


@pytest.mark.usefixtures("with_request_context")
def test_user_generate_apikey_for_another_user(mock_user_factory):
    fred = mock_user_factory(name="fred")
    bob = mock_user_factory(name="bob")
    mock_model = mock.MagicMock()
    mock_model.User.get.return_value = fred
    # auth_user_obj shows user as logged in for non-anonymous auth
    # functions
    context = {"model": mock_model, "auth_user_obj": bob}
    context["user"] = bob.name
    params = {"id": fred.id}

    with pytest.raises(logic.NotAuthorized):
        helpers.call_auth("user_generate_apikey", context=context, **params)


@pytest.mark.ckan_config("ckan.plugins", "image_view")
@pytest.mark.usefixtures("clean_db", "with_plugins", "with_request_context")
class TestUpdateWithView(object):
    def test_anon_can_not_update(self, resource_view):
        params = {
            "id": resource_view["id"],
            "title": "Resource View Updated",
            "view_type": "image_view",
            "image_url": "url",
        }

        context = {"user": None, "model": model}
        with pytest.raises(logic.NotAuthorized):
            helpers.call_auth(
                "resource_view_update", context=context, **params
            )

    def test_authorized_if_user_has_permissions_on_dataset(self, user, package_factory, resource_factory, resource_view_factory):

        dataset = package_factory(user=user)

        resource = resource_factory(user=user, package_id=dataset["id"])

        resource_view = resource_view_factory(resource_id=resource["id"])

        params = {
            "id": resource_view["id"],
            "resource_id": resource["id"],
            "title": "Resource View Updated",
            "view_type": "image_view",
            "image_url": "url",
        }

        context = {"user": user["name"], "model": model}
        response = helpers.call_auth(
            "resource_view_update", context=context, **params
        )

        assert response

    def test_not_authorized_if_user_has_no_permissions_on_dataset(self, organization, user_factory, package_factory, resource_factory, resource_view_factory):
        user = user_factory()

        member = {"username": user["name"], "role": "admin", "id": organization["id"]}
        helpers.call_action("organization_member_create", **member)

        user_2 = user_factory()

        dataset = package_factory(owner_org=organization["id"])

        resource = resource_factory(package_id=dataset["id"])

        resource_view = resource_view_factory(resource_id=resource["id"])

        params = {
            "id": resource_view["id"],
            "resource_id": resource["id"],
            "title": "Resource View Updated",
            "view_type": "image_view",
            "image_url": "url",
        }

        context = {"user": user_2["name"], "model": model}
        with pytest.raises(logic.NotAuthorized):
            helpers.call_auth(
                "resource_view_update", context=context, **params
            )


@pytest.mark.usefixtures("clean_db", "with_request_context")
class TestUpdate(object):
    def test_config_option_update_anon_user(self):
        """An anon user is not authorized to use config_option_update
        action."""
        context = {"user": None, "model": None}
        with pytest.raises(logic.NotAuthorized):
            helpers.call_auth("config_option_update", context=context)

    def test_config_option_update_normal_user(self, user):
        """A normal logged in user is not authorized to use config_option_update
        action."""
        context = {"user": user["name"], "model": None}
        with pytest.raises(logic.NotAuthorized):
            helpers.call_auth("config_option_update", context=context)

    def test_config_option_update_sysadmin(self, sysadmin):
        """A sysadmin is authorized to use config_option_update action."""
        context = {"user": sysadmin["name"], "model": None}
        assert helpers.call_auth("config_option_update", context=context)


@pytest.mark.usefixtures('clean_db', 'with_plugins')
@pytest.mark.ckan_config('ckan.plugins', 'image_view')
@pytest.mark.ckan_config('ckan.auth.allow_dataset_collaborators', True)
@pytest.mark.ckan_config('ckan.auth.allow_admin_collaborators', True)
class TestUpdateAuthWithCollaborators(object):

    def _get_context(self, user):

        return {
            'model': model,
            'user': user if isinstance(user, str) else user.get('name')
        }

    @pytest.mark.parametrize('role,action,private', [
        ('admin', 'package_update', False),
        ('editor', 'package_update', False),
        ('admin', 'package_update', True),
        ('editor', 'package_update', True),
        ('admin', 'package_delete', False),
        ('editor', 'package_delete', False),
        ('admin', 'package_delete', True),
        ('editor', 'package_delete', True),
    ])
    def test_dataset_manage_admin_and_editors(self, role, action, private, organization, user, package_factory):
        dataset = package_factory(owner_org=organization['id'], private=private)
        context = self._get_context(user)
        with pytest.raises(logic.NotAuthorized):
            helpers.call_auth(
                action,
                context=context, id=dataset['id'])

        helpers.call_action(
            'package_collaborator_create',
            id=dataset['id'], user_id=user['id'], capacity=role)

        assert helpers.call_auth(
            action,
            context=context, id=dataset['id'])

    @pytest.mark.parametrize('action,private', [
        ('package_update', False),
        ('package_update', False),
        ('package_update', True),
        ('package_update', True),
        ('package_delete', False),
        ('package_delete', False),
        ('package_delete', True),
        ('package_delete', True),
    ])
    def test_dataset_manage_member(self, action, private, organization, user, package_factory):
        dataset = package_factory(owner_org=organization['id'], private=private)

        context = self._get_context(user)
        with pytest.raises(logic.NotAuthorized):
            helpers.call_auth(
                action,
                context=context, id=dataset['id'])

        helpers.call_action(
            'package_collaborator_create',
            id=dataset['id'], user_id=user['id'], capacity='member')

        context = self._get_context(user)
        with pytest.raises(logic.NotAuthorized):
            helpers.call_auth(
                action,
                context=context, id=dataset['id'])

    @pytest.mark.parametrize('role', ['admin', 'editor'])
    def test_resource_create_public_admin_and_editor(self, role, organization, user, package_factory):
        dataset = package_factory(owner_org=organization['id'])

        context = self._get_context(user)
        with pytest.raises(logic.NotAuthorized):
            helpers.call_auth(
                'resource_create',
                context=context, package_id=dataset['id'])

        helpers.call_action(
            'package_collaborator_create',
            id=dataset['id'], user_id=user['id'], capacity=role)

        assert helpers.call_auth(
            'resource_create',
            context=context, package_id=dataset['id'])

    def test_resource_create_public_member(self, organization, user, package_factory):

        dataset = package_factory(owner_org=organization['id'])

        context = self._get_context(user)
        with pytest.raises(logic.NotAuthorized):
            helpers.call_auth(
                'resource_create',
                context=context, package_id=dataset['id'])

        helpers.call_action(
            'package_collaborator_create',
            id=dataset['id'], user_id=user['id'], capacity='member')

        with pytest.raises(logic.NotAuthorized):
            helpers.call_auth(
                'resource_create',
                context=context, package_id=dataset['id'])

    @pytest.mark.parametrize('role,action', [
        ('admin', 'resource_update'),
        ('editor', 'resource_update'),
        ('admin', 'resource_delete'),
        ('editor', 'resource_delete'),
    ])
    def test_resource_manage_public_admin_and_editor(self, role, action, organization, user, package_factory, resource_factory):

        dataset = package_factory(owner_org=organization['id'])
        resource = resource_factory(package_id=dataset['id'])

        context = self._get_context(user)
        with pytest.raises(logic.NotAuthorized):
            helpers.call_auth(
                action,
                context=context, id=resource['id'])

        helpers.call_action(
            'package_collaborator_create',
            id=dataset['id'], user_id=user['id'], capacity=role)

        assert helpers.call_auth(
            action,
            context=context, id=resource['id'])

    def test_resource_update_public_member(self, organization, user, package_factory, resource_factory):

        dataset = package_factory(owner_org=organization['id'])
        resource = resource_factory(package_id=dataset['id'])

        context = self._get_context(user)
        with pytest.raises(logic.NotAuthorized):
            helpers.call_auth(
                'resource_update',
                context=context, id=resource['id'])

        helpers.call_action(
            'package_collaborator_create',
            id=dataset['id'], user_id=user['id'], capacity='member')

        with pytest.raises(logic.NotAuthorized):
            helpers.call_auth(
                'resource_update',
                context=context, id=resource['id'])

    def test_resource_delete_public_member(self, organization, user, package_factory, resource_factory):
        dataset = package_factory(owner_org=organization['id'])
        resource = resource_factory(package_id=dataset['id'])

        context = self._get_context(user)
        with pytest.raises(logic.NotAuthorized):
            helpers.call_auth(
                'resource_delete',
                context=context, id=resource['id'])

        helpers.call_action(
            'package_collaborator_create',
            id=dataset['id'], user_id=user['id'], capacity='member')

        with pytest.raises(logic.NotAuthorized):
            helpers.call_auth(
                'resource_delete',
                context=context, id=resource['id'])

    @pytest.mark.parametrize('role', ['admin', 'editor'])
    def test_resource_view_create_public_editor(self, role, organization, user, package_factory, resource_factory):

        dataset = package_factory(owner_org=organization['id'])
        resource = resource_factory(package_id=dataset['id'])

        context = self._get_context(user)
        with pytest.raises(logic.NotAuthorized):
            helpers.call_auth(
                'resource_view_create',
                context=context, resource_id=resource['id'])

        helpers.call_action(
            'package_collaborator_create',
            id=dataset['id'], user_id=user['id'], capacity=role)

        assert helpers.call_auth(
            'resource_view_create',
            context=context, resource_id=resource['id'])

    def test_resource_view_create_public_member(self, organization, user, package_factory, resource_factory):

        dataset = package_factory(owner_org=organization['id'])
        resource = resource_factory(package_id=dataset['id'])

        context = self._get_context(user)
        with pytest.raises(logic.NotAuthorized):
            helpers.call_auth(
                'resource_view_create',
                context=context, resource_id=resource['id'])

        helpers.call_action(
            'package_collaborator_create',
            id=dataset['id'], user_id=user['id'], capacity='member')

        with pytest.raises(logic.NotAuthorized):
            helpers.call_auth(
                'resource_view_create',
                context=context, resource_id=resource['id'])
