# encoding: utf-8

from bs4 import BeautifulSoup
from werkzeug.routing import BuildError
import unittest.mock as mock

import ckan.authz as authz
from ckan.lib.helpers import url_for
import pytest
import six
from urllib.parse import urlparse
import ckan.model as model
import ckan.model.activity as activity_model
import ckan.plugins as p
import ckan.lib.dictization as dictization
import ckan.logic as logic

from ckan.logic.validators import object_id_validators, package_id_exists

import ckan.tests.helpers as helpers
import ckan.tests.factories as factories


@pytest.fixture
def user_env(user):
    return {"REMOTE_USER": six.ensure_str(user["name"])}


def _get_location(res):
    location = res.headers['location']
    return urlparse(location)._replace(scheme='', netloc='').geturl()


@pytest.mark.usefixtures("clean_db", "with_request_context")
class TestPackageNew(object):

    @pytest.mark.ckan_config("ckan.plugins", "test_package_controller_plugin")
    @pytest.mark.usefixtures("with_plugins")
    def test_new_plugin_hook(self, app, user):
        plugin = p.get_plugin("test_package_controller_plugin")
        res = app.post(
            url_for("dataset.new"),
            extra_environ={"REMOTE_USER": user["name"]},
            data={"name": u"plugged", "save": ""},
            follow_redirects=False,
        )
        assert plugin.calls["edit"] == 0, plugin.calls
        assert plugin.calls["create"] == 1, plugin.calls

    @pytest.mark.ckan_config("ckan.plugins", "test_package_controller_plugin")
    @pytest.mark.usefixtures("with_plugins")
    def test_after_create_plugin_hook(self, app, user):
        plugin = p.get_plugin("test_package_controller_plugin")
        res = app.post(
            url_for("dataset.new"),
            extra_environ={"REMOTE_USER": user["name"]},
            data={"name": u"plugged2", "save": ""},
            follow_redirects=False,
        )
        assert plugin.calls["after_update"] == 0, plugin.calls
        assert plugin.calls["after_create"] == 1, plugin.calls

        assert plugin.id_in_dict

    @pytest.mark.usefixtures("clean_index")
    def test_new_indexerror(self, app, user):
        from ckan.lib.search.common import SolrSettings
        bad_solr_url = "http://example.com/badsolrurl"
        solr_url = SolrSettings.get()[0]
        try:
            SolrSettings.init(bad_solr_url)
            new_package_name = u"new-package-missing-solr"

            offset = url_for("dataset.new")
            res = app.post(
                offset,
                extra_environ={"REMOTE_USER": user["name"]},
                data={"save": "", "name": new_package_name},
            )
            assert "Unable to add package to search index" in res, res
        finally:
            SolrSettings.init(solr_url)

    def test_change_locale(self, app, user):
        url = url_for("dataset.new")
        res = app.get(url, extra_environ={"REMOTE_USER": user["name"]})
        res = app.get("/de/dataset/new", extra_environ={"REMOTE_USER": user["name"]})
        assert helpers.body_contains(res, "Datensatz")

    @pytest.mark.ckan_config("ckan.auth.create_unowned_dataset", "false")
    def test_needs_organization_but_no_organizations_has_button(self, app, sysadmin):
        """ Scenario: The settings say every dataset needs an organization
        but there are no organizations. If the user is allowed to create an
        organization they should be prompted to do so when they try to create
        a new dataset"""
        env = {"REMOTE_USER": six.ensure_str(sysadmin["name"])}
        response = app.get(url=url_for("dataset.new"), extra_environ=env)
        assert url_for("organization.new") in response

    @pytest.mark.ckan_config("ckan.auth.create_unowned_dataset", "false")
    @pytest.mark.ckan_config("ckan.auth.user_create_organizations", "false")
    def test_needs_organization_but_no_organizations_no_button(
            self, monkeypatch, app, user
    ):
        """ Scenario: The settings say every dataset needs an organization
        but there are no organizations. If the user is not allowed to create an
        organization they should be told to ask the admin but no link should be
        presented. Note: This cannot happen with the default ckan and requires
        a plugin to overwrite the package_create behavior"""
        authz._AuthFunctions.get('package_create')
        monkeypatch.setitem(
            authz._AuthFunctions._functions, 'package_create',
            lambda *args: {'success': True})

        env = {"REMOTE_USER": six.ensure_str(user["name"])}
        response = app.get(url=url_for("dataset.new"), extra_environ=env)

        assert url_for("organization.new") not in response
        assert "Ask a system administrator" in response

    def test_name_required(self, app, user_env):
        url = url_for("dataset.new")
        response = app.post(url, environ_overrides=user_env, data={"save": ""})
        assert "Name: Missing value" in response

    def test_first_page_creates_draft_package(self, app, user_env):
        url = url_for("dataset.new")
        response = app.post(url, environ_overrides=user_env, data={
            "name": "first-page-creates-draft",
            "save": "",
            "_ckan_phase": 1
        }, follow_redirects=False)
        pkg = model.Package.by_name(u"first-page-creates-draft")
        assert pkg.state == "draft"

    def test_resource_required(self, app, user_env):
        url = url_for("dataset.new")
        name = "one-resource-required"
        response = app.post(url, environ_overrides=user_env, data={
            "name": name,
            "save": "",
            "_ckan_phase": 1
        }, follow_redirects=False)
        location = _get_location(response)
        response = app.post(location, environ_overrides=user_env, data={
            "id": "",
            "url": "",
            "save": "go-metadata",
        })
        assert "You must add at least one data resource" in response

    def test_complete_package_with_one_resource(self, app, user_env):
        url = url_for("dataset.new")
        response = app.post(url, environ_overrides=user_env, data={
            "name": "complete-package-with-one-resource",
            "save": "",
            "_ckan_phase": 1

        }, follow_redirects=False)
        location = _get_location(response)
        response = app.post(location, environ_overrides=user_env, data={
            "id": "",
            "url": "http://example.com/resource",
            "save": "go-metadata"
        })

        pkg = model.Package.by_name(u"complete-package-with-one-resource")
        assert pkg.resources[0].url == u"http://example.com/resource"
        assert pkg.state == "active"

    def test_complete_package_with_two_resources(self, app, user_env):
        url = url_for("dataset.new")
        response = app.post(url, environ_overrides=user_env, data={
            "name": "complete-package-with-two-resources",
            "save": "",
            "_ckan_phase": 1
        }, follow_redirects=False)
        location = _get_location(response)
        app.post(location, environ_overrides=user_env, data={
            "id": "",
            "url": "http://example.com/resource0",
            "save": "again"
        })
        app.post(location, environ_overrides=user_env, data={
            "id": "",
            "url": "http://example.com/resource1",
            "save": "go-metadata"
        })
        pkg = model.Package.by_name(u"complete-package-with-two-resources")
        assert pkg.resources[0].url == u"http://example.com/resource0"
        assert pkg.resources[1].url == u"http://example.com/resource1"
        assert pkg.state == "active"

    # resource upload is tested in TestExampleIUploaderPlugin

    def test_previous_button_works(self, app, user_env):
        url = url_for("dataset.new")
        response = app.post(url, environ_overrides=user_env, data={
            "name": "previous-button-works",
            "save": "",
            "_ckan_phase": 1
        }, follow_redirects=False)

        location = _get_location(response)
        response = app.post(location, environ_overrides=user_env, data={
            "id": "",
            "save": "go-dataset"
        }, follow_redirects=False)

        assert '/dataset/edit/' in response.headers['location']

    def test_previous_button_populates_form(self, app, user_env):
        url = url_for("dataset.new")
        response = app.post(url, environ_overrides=user_env, data={
            "name": "previous-button-populates-form",
            "save": "",
            "_ckan_phase": 1
        }, follow_redirects=False)

        location = _get_location(response)
        response = app.post(location, environ_overrides=user_env, data={
            "id": "",
            "save": "go-dataset"
        })

        assert 'name="title"' in response
        assert 'value="previous-button-populates-form"'

    def test_previous_next_maintains_draft_state(self, app, user_env):
        url = url_for("dataset.new")
        response = app.post(url, environ_overrides=user_env, data={
            "name": "previous-next-maintains-draft",
            "save": "",
            "_ckan_phase": 1
        }, follow_redirects=False)

        location = _get_location(response)
        response = app.post(location, environ_overrides=user_env, data={
            "id": "",
            "save": "go-dataset"
        })

        pkg = model.Package.by_name(u"previous-next-maintains-draft")
        assert pkg.state == "draft"

    def test_dataset_edit_org_dropdown_visible_to_normal_user_with_orgs_available(
            self, app, user, organization_factory
    ):
        """
        The 'Organization' dropdown is available on the dataset create/edit
        page to normal (non-sysadmin) users who have organizations available
        to them.
        """
        # user is admin of org.
        org = organization_factory(
            name="my-org", users=[{"name": user["id"], "capacity": "admin"}]
        )

        env = {"REMOTE_USER": six.ensure_str(user["name"])}

        url = url_for("dataset.new")
        response = app.post(url, environ_overrides=env, data={
            "name": "my-dataset",
            "owner_org": org["id"],
            "save": "",
            "_ckan_phase": 1
        }, follow_redirects=False)
        location = _get_location(response)
        response = app.post(location, environ_overrides=env, data={
            "id": "",
            "url": "http://example.com/resource",
            "save": "go-metadata"
        })

        pkg = model.Package.by_name(u"my-dataset")
        assert pkg.state == "active"

        # edit package page response
        url = url_for("dataset.edit", id=pkg.id)
        pkg_edit_response = app.get(url=url, extra_environ=env)
        # A field with the correct id is in the response

        owner_org_options = [
            option['value'] for option
            in BeautifulSoup(pkg_edit_response.data).body.select(
                "form#dataset-edit"
            )[0].select('[name=owner_org]')[0].select('option')
        ]
        assert org["id"] in owner_org_options

    def test_dataset_edit_org_dropdown_normal_user_can_remove_org(self, app, user_env, user, organization_factory):
        """
        A normal user (non-sysadmin) can remove an organization from a dataset
        have permissions on.
        """
        # user is admin of org.
        org = organization_factory(
            name="my-org", users=[{"name": user["id"], "capacity": "admin"}]
        )

        env = {"REMOTE_USER": six.ensure_str(user["name"])}

        url = url_for("dataset.new")
        response = app.post(url, environ_overrides=env, data={
            "name": "my-dataset",
            "owner_org": org["id"],
            "save": "",
            "_ckan_phase": 1
        }, follow_redirects=False)
        location = _get_location(response)
        response = app.post(location, environ_overrides=env, data={
            "id": "",
            "url": "http://example.com/resource",
            "save": "go-metadata"
        })

        pkg = model.Package.by_name(u"my-dataset")
        assert pkg.state == "active"
        assert pkg.owner_org == org["id"]
        assert pkg.owner_org is not None
        # edit package page response
        url = url_for("dataset.edit", id=pkg.id)
        pkg_edit_response = app.post(url=url, extra_environ=env, data={"owner_org": ""}, follow_redirects=False)

        post_edit_pkg = model.Package.by_name(u"my-dataset")
        assert post_edit_pkg.owner_org is None
        assert post_edit_pkg.owner_org != org["id"]

    def test_dataset_edit_org_dropdown_not_visible_to_normal_user_with_no_orgs_available(
            self, app, user_env, user, organization_factory
    ):
        """
        The 'Organization' dropdown is not available on the dataset
        create/edit page to normal (non-sysadmin) users who have no
        organizations available to them.
        """
        # user isn't admin of org.
        org = organization_factory(name="my-org")

        env = {"REMOTE_USER": six.ensure_str(user["name"])}
        url = url_for("dataset.new")
        response = app.post(url, environ_overrides=env, data={
            "name": "my-dataset",
            "save": "",
            "_ckan_phase": 1
        }, follow_redirects=False)
        location = _get_location(response)
        response = app.post(location, environ_overrides=env, data={
            "id": "",
            "url": "http://example.com/resource",
            "save": "go-metadata"
        })

        pkg = model.Package.by_name(u"my-dataset")
        assert pkg.state == "active"

        # edit package response
        url = url_for(
            "dataset.edit", id=model.Package.by_name(u"my-dataset").id
        )
        pkg_edit_response = app.get(url=url, extra_environ=env)
        # A field with the correct id is in the response
        assert 'value="{0}"'.format(org["id"]) not in pkg_edit_response

    def test_dataset_edit_org_dropdown_visible_to_sysadmin_with_no_orgs_available(
            self, app, user_env, user, sysadmin, organization_factory
    ):
        """
        The 'Organization' dropdown is available to sysadmin users regardless
        of whether they personally have an organization they administrate.
        """
        # user is admin of org.
        org = organization_factory(
            name="my-org", users=[{"name": user["id"], "capacity": "admin"}]
        )

        # user in env is sysadmin
        env = {"REMOTE_USER": six.ensure_str(sysadmin["name"])}
        url = url_for("dataset.new")
        response = app.get(url=url, extra_environ=env)
        # organization dropdown available in create page.
        assert 'id="field-organizations"' in response

        response = app.post(url, environ_overrides=env, data={
            "name": "my-dataset",
            "owner_org": org["id"],
            "save": "",
            "_ckan_phase": 1
        }, follow_redirects=False)
        location = _get_location(response)
        response = app.post(location, environ_overrides=env, data={
            "id": "",
            "url": "http://example.com/resource",
            "save": "go-metadata"
        })

        pkg = model.Package.by_name(u"my-dataset")
        assert pkg.state == "active"

        # edit package page response
        url = url_for("dataset.edit", id=pkg.id)
        pkg_edit_response = app.get(url=url, extra_environ=env)
        # A field with the correct id is in the response
        assert 'id="field-organizations"' in pkg_edit_response
        # The organization id is in the response in a value attribute
        assert 'value="{0}"'.format(org["id"]) in pkg_edit_response

    def test_unauthed_user_creating_dataset(self, app):

        # provide REMOTE_ADDR to idenfity as remote user, see
        # ckan.views.identify_user() for details
        response = app.post(
            url=url_for("dataset.new"),
            extra_environ={"REMOTE_ADDR": "127.0.0.1"},
            status=403,
        )

    def test_form_without_initial_data(self, app, user):
        env = {"REMOTE_USER": six.ensure_str(user["name"])}
        url = url_for("dataset.new")
        resp = app.get(url=url, extra_environ=env)
        page = BeautifulSoup(resp.body)
        form = page.select_one('#dataset-edit')
        assert not form.select_one('[name=title]')['value']
        assert not form.select_one('[name=name]')['value']
        assert not form.select_one('[name=notes]').text

    def test_form_with_initial_data(self, app, user):
        env = {"REMOTE_USER": six.ensure_str(user["name"])}
        url = url_for("dataset.new", name="name",
                      notes="notes", title="title")
        resp = app.get(url=url, extra_environ=env)
        page = BeautifulSoup(resp.body)
        form = page.select_one('#dataset-edit')
        assert form.select_one('[name=title]')['value'] == "title"
        assert form.select_one('[name=name]')['value'] == "name"
        assert form.select_one('[name=notes]').text == "notes"


@pytest.mark.usefixtures("clean_db", "with_request_context")
class TestPackageEdit(object):
    def test_redirect_after_edit_using_param(self, app, package, sysadmin):
        return_url = "http://random.site.com/dataset/<NAME>?test=param"
        url = url_for("dataset.edit", id=package["name"], return_to=return_url)
        resp = app.post(url, extra_environ={"REMOTE_USER": sysadmin["name"]}, follow_redirects=False)
        assert resp.headers["location"] == return_url.replace("<NAME>", package["name"])

    def test_redirect_after_edit_using_config(self, app, ckan_config, package, sysadmin):
        expected_redirect = ckan_config["package_edit_return_url"]
        url = url_for("dataset.edit", id=package["name"])
        resp = app.post(url, extra_environ={"REMOTE_USER": sysadmin["name"]}, follow_redirects=False)
        assert resp.headers["location"] == expected_redirect.replace("<NAME>", package["name"])

    def test_organization_admin_can_edit(self, app, user, organization_factory, package_factory):
        organization = organization_factory(
            users=[{"name": user["id"], "capacity": "admin"}]
        )
        dataset = package_factory(owner_org=organization["id"])
        env = {"REMOTE_USER": six.ensure_str(user["name"])}
        response = app.post(
            url_for("dataset.edit", id=dataset["name"]), extra_environ=env,
            data={
                "notes": u"edited description",
                "save": ""
            }, follow_redirects=False
        )
        result = helpers.call_action("package_show", id=dataset["id"])
        assert u"edited description" == result["notes"]

    def test_organization_editor_can_edit(self, app, user, organization_factory, package_factory):
        organization = organization_factory(
            users=[{"name": user["id"], "capacity": "editor"}]
        )
        dataset = package_factory(owner_org=organization["id"])
        env = {"REMOTE_USER": six.ensure_str(user["name"])}
        response = app.post(
            url_for("dataset.edit", id=dataset["name"]), extra_environ=env,
            data={
                "notes": u"edited description",
                "save": ""
            }, follow_redirects=False

        )
        result = helpers.call_action("package_show", id=dataset["id"])
        assert u"edited description" == result["notes"]

    def test_organization_member_cannot_edit(self, app, user, organization_factory, package_factory):
        organization = organization_factory(
            users=[{"name": user["id"], "capacity": "member"}]
        )
        dataset = package_factory(owner_org=organization["id"])
        env = {"REMOTE_USER": six.ensure_str(user["name"])}
        response = app.get(
            url_for("dataset.edit", id=dataset["name"]),
            extra_environ=env,
            status=403,
        )

    def test_user_not_in_organization_cannot_edit(self, app, user, organization, package_factory):
        dataset = package_factory(owner_org=organization["id"])
        env = {"REMOTE_USER": six.ensure_str(user["name"])}
        response = app.get(
            url_for("dataset.edit", id=dataset["name"]),
            extra_environ=env,
            status=403,
        )

        env = {"REMOTE_USER": six.ensure_str(user["name"])}
        response = app.post(
            url_for("dataset.edit", id=dataset["name"]),
            data={"notes": "edited description"},
            extra_environ=env,
            status=403,
        )

    def test_anonymous_user_cannot_edit(self, app, organization, package_factory):
        dataset = package_factory(owner_org=organization["id"])
        response = app.get(
            url_for("dataset.edit", id=dataset["name"]), status=403
        )

        response = app.post(
            url_for("dataset.edit", id=dataset["name"]),
            data={"notes": "edited description"},
            status=403,
        )

    def test_validation_errors_for_dataset_name_appear(self, app, user, organization_factory, package_factory):
        """fill out a bad dataset set name and make sure errors appear"""
        organization = organization_factory(
            users=[{"name": user["id"], "capacity": "admin"}]
        )
        dataset = package_factory(owner_org=organization["id"])
        env = {"REMOTE_USER": six.ensure_str(user["name"])}
        response = app.post(
            url_for("dataset.edit", id=dataset["name"]), extra_environ=env,
            data={
                "name": "this is not a valid name",
                "save": ""
            }
        )
        assert "The form contains invalid entries" in response.body

        assert (
            "Name: Must be purely lowercase alphanumeric (ascii) "
            "characters and these symbols: -_" in response.body
        )

    def test_edit_a_dataset_that_does_not_exist_404s(self, app, user):
        env = {"REMOTE_USER": six.ensure_str(user["name"])}
        response = app.get(
            url_for("dataset.edit", id="does-not-exist"),
            extra_environ=env,

        )
        assert 404 == response.status_code


@pytest.mark.usefixtures("clean_db", "with_request_context")
class TestPackageOwnerOrgList(object):

    owner_org_select = '<select id="field-organizations" name="owner_org"'

    def test_org_list_shown_if_new_dataset_and_user_is_admin_or_editor_in_an_org(self, app, user, organization_factory):
        organization = organization_factory(
            users=[{"name": user["id"], "capacity": "admin"}]
        )
        env = {"REMOTE_USER": six.ensure_str(user["name"])}
        response = app.get(
            url_for("dataset.new"), extra_environ=env
        )
        assert self.owner_org_select in response.body

    def test_org_list_shown_if_admin_or_editor_of_the_dataset_org(self, app, user, organization_factory, package_factory):
        organization = organization_factory(
            users=[{"name": user["id"], "capacity": "admin"}]
        )
        dataset = package_factory(owner_org=organization["id"])
        env = {"REMOTE_USER": six.ensure_str(user["name"])}
        response = app.get(
            url_for("dataset.edit", id=dataset["name"]), extra_environ=env
        )
        assert self.owner_org_select in response.body

    @pytest.mark.ckan_config('ckan.auth.allow_dataset_collaborators', True)
    def test_org_list_not_shown_if_user_is_a_collaborator_with_default_config(self, app, user, organization_factory, package_factory):

        organization1 = organization_factory()
        dataset = package_factory(owner_org=organization1["id"])

        organization2 = organization_factory(
            users=[{"name": user["id"], "capacity": "admin"}]
        )
        helpers.call_action(
            'package_collaborator_create',
            id=dataset['id'], user_id=user['id'], capacity='editor')

        env = {"REMOTE_USER": six.ensure_str(user["name"])}
        response = app.get(
            url_for("dataset.edit", id=dataset["name"]), extra_environ=env
        )
        assert self.owner_org_select not in response.body

        response = app.post(
            url_for("dataset.edit", id=dataset["name"]), extra_environ=env,
            data={
                "notes": "changed",
                "save": ""
            },
            follow_redirects=False
        )
        updated_dataset = helpers.call_action("package_show", id=dataset["id"])
        assert updated_dataset['owner_org'] == organization1['id']

    @pytest.mark.ckan_config('ckan.auth.allow_dataset_collaborators', True)
    @pytest.mark.ckan_config('ckan.auth.allow_collaborators_to_change_owner_org', True)
    def test_org_list_shown_if_user_is_a_collaborator_with_config_enabled(self, app, user, organization_factory, package_factory):

        organization1 = organization_factory()
        dataset = package_factory(owner_org=organization1["id"])

        organization2 = organization_factory(
            users=[{"name": user["id"], "capacity": "admin"}]
        )
        helpers.call_action(
            'package_collaborator_create',
            id=dataset['id'], user_id=user['id'], capacity='editor')

        env = {"REMOTE_USER": six.ensure_str(user["name"])}
        response = app.get(
            url_for("dataset.edit", id=dataset["name"]), extra_environ=env,
        )
        assert self.owner_org_select in response.body

        response = app.post(
            url_for("dataset.edit", id=dataset["name"]), extra_environ=env,
            data={
                "notes": "changed",
                "owner_org": organization2['id'],
                "save": ""
            },
            follow_redirects=False
        )
        updated_dataset = helpers.call_action("package_show", id=dataset["id"])
        assert updated_dataset['owner_org'] == organization2['id']


@pytest.mark.usefixtures("clean_db", "with_request_context")
class TestPackageRead(object):
    def test_read(self, app, package):
        response = app.get(url_for("dataset.read", id=package["name"]))
        assert helpers.body_contains(response, "Test Dataset")
        assert helpers.body_contains(response, "Just another test dataset")

    def test_organization_members_can_read_private_datasets(self, app, user_factory, sysadmin_factory, organization_factory, package_factory):
        members = {
            "member": user_factory(),
            "editor": user_factory(),
            "admin": user_factory(),
            "sysadmin": sysadmin_factory(),
        }
        organization = organization_factory(
            users=[
                {"name": members["member"]["id"], "capacity": "member"},
                {"name": members["editor"]["id"], "capacity": "editor"},
                {"name": members["admin"]["id"], "capacity": "admin"},
            ]
        )
        dataset = package_factory(owner_org=organization["id"], private=True)
        for user, user_dict in members.items():
            response = app.get(
                url_for("dataset.read", id=dataset["name"]),
                extra_environ={
                    "REMOTE_USER": six.ensure_str(user_dict["name"])
                },
            )
            assert "Test Dataset" in response.body
            assert "Just another test dataset" in response.body

    def test_anonymous_users_cannot_read_private_datasets(self, app, package_factory, organization):
        dataset = package_factory(owner_org=organization["id"], private=True)
        response = app.get(
            url_for("dataset.read", id=dataset["name"]), status=404
        )
        assert 404 == response.status_code

    def test_user_not_in_organization_cannot_read_private_datasets(self, app, user, package_factory, organization):
        dataset = package_factory(owner_org=organization["id"], private=True)
        response = app.get(
            url_for("dataset.read", id=dataset["name"]),
            extra_environ={"REMOTE_USER": six.ensure_str(user["name"])},
            status=404,
        )
        assert 404 == response.status_code

    def test_read_rdf(self, app, package):
        """ The RDF outputs now live in ckanext-dcat"""
        offset = url_for("dataset.read", id=package["name"]) + ".rdf"
        app.get(offset, status=404)

    def test_read_n3(self, app, package):
        """ The RDF outputs now live in ckanext-dcat"""
        offset = url_for("dataset.read", id=package["name"]) + ".n3"
        app.get(offset, status=404)

    def test_read_dataset_as_it_used_to_be(self, app, sysadmin, package_factory):
        dataset = package_factory(title="Original title")
        activity = (
            model.Session.query(model.Activity)
            .filter_by(object_id=dataset["id"])
            .one()
        )
        dataset["title"] = "Changed title"
        helpers.call_action("package_update", **dataset)

        env = {"REMOTE_USER": six.ensure_str(sysadmin["name"])}
        response = app.get(
            url_for(
                "dataset.read", id=dataset["name"], activity_id=activity.id
            ),
            extra_environ=env,
        )
        assert helpers.body_contains(response, "Original title")

    def test_read_dataset_as_it_used_to_be_but_is_unmigrated(self, app, user, sysadmin, package_factory):
        # Renders the dataset using the activity detail, when that Activity was
        # created with an earlier version of CKAN, and it has not been migrated
        # (with migrate_package_activity.py), which should give a 404

        dataset = package_factory(user=user)

        # delete the modern Activity object that's been automatically created
        modern_activity = (
            model.Session.query(model.Activity)
            .filter_by(object_id=dataset["id"])
            .one()
        )
        modern_activity.delete()

        # Create an Activity object as it was in earlier versions of CKAN.
        # This code is based on:
        # https://github.com/ckan/ckan/blob/b348bf2fe68db6704ea0a3e22d533ded3d8d4344/ckan/model/package.py#L508
        activity_type = "changed"
        dataset_table_dict = dictization.table_dictize(
            model.Package.get(dataset["id"]), context={"model": model}
        )
        activity = model.Activity(
            user_id=user["id"],
            object_id=dataset["id"],
            activity_type="%s package" % activity_type,
            data={
                # "actor": a legacy activity had no "actor"
                # "package": a legacy activity had just the package table,
                # rather than the result of package_show
                "package": dataset_table_dict
            },
        )
        model.Session.add(activity)
        # a legacy activity had a ActivityDetail associated with the Activity
        # This code is based on:
        # https://github.com/ckan/ckan/blob/b348bf2fe68db6704ea0a3e22d533ded3d8d4344/ckan/model/package.py#L542
        activity_detail = model.ActivityDetail(
            activity_id=activity.id,
            object_id=dataset["id"],
            object_type=u"Package",
            activity_type=activity_type,
            data={u"package": dataset_table_dict},
        )
        model.Session.add(activity_detail)
        model.Session.flush()

        env = {"REMOTE_USER": six.ensure_str(sysadmin["name"])}
        response = app.get(
            url_for(
                "dataset.read", id=dataset["name"], activity_id=activity.id
            ),
            extra_environ=env,
            status=404,
        )


@pytest.mark.usefixtures("clean_db", "with_request_context")
class TestPackageDelete(object):
    def test_owner_delete(self, app, user, organization_factory, package_factory):
        owner_org = organization_factory(
            users=[{"name": user["id"], "capacity": "admin"}]
        )
        dataset = package_factory(owner_org=owner_org["id"])

        env = {"REMOTE_USER": six.ensure_str(user["name"])}
        response = app.post(
            url_for("dataset.delete", id=dataset["name"]), extra_environ=env
        )
        assert 200 == response.status_code

        deleted = helpers.call_action("package_show", id=dataset["id"])
        assert "deleted" == deleted["state"]

    def test_delete_on_non_existing_dataset(self, app):
        response = app.post(
            url_for("dataset.delete", id="schrodingersdatset"),

        )
        assert 404 == response.status_code

    def test_sysadmin_can_delete_any_dataset(self, app, package_factory, organization, sysadmin):
        dataset = package_factory(owner_org=organization["id"])

        env = {"REMOTE_USER": six.ensure_str(sysadmin["name"])}

        response = app.post(
            url_for("dataset.delete", id=dataset["name"]), extra_environ=env
        )
        assert 200 == response.status_code

        deleted = helpers.call_action("package_show", id=dataset["id"])
        assert "deleted" == deleted["state"]

    def test_anon_user_cannot_delete_owned_dataset(self, app, user, organization_factory, package_factory):
        owner_org = organization_factory(
            users=[{"name": user["id"], "capacity": "admin"}]
        )
        dataset = package_factory(owner_org=owner_org["id"])

        response = app.post(
            url_for("dataset.delete", id=dataset["name"]), status=403
        )
        assert helpers.body_contains(response, "Unauthorized to delete package")

        deleted = helpers.call_action("package_show", id=dataset["id"])
        assert "active" == deleted["state"]

    def test_logged_in_user_cannot_delete_owned_dataset(self, app, user, user_factory, organization_factory, package_factory):
        owner = user_factory()
        owner_org = organization_factory(
            users=[{"name": owner["id"], "capacity": "admin"}]
        )
        dataset = package_factory(owner_org=owner_org["id"])

        env = {"REMOTE_USER": six.ensure_str(user["name"])}
        response = app.post(
            url_for("dataset.delete", id=dataset["name"]),
            extra_environ=env,

        )
        assert 403 == response.status_code
        assert helpers.body_contains(response, "Unauthorized to delete package")

    def test_confirm_cancel_delete(self, app, user, organization_factory, package_factory):
        """Test confirmation of deleting datasets

        When package_delete is made as a get request, it should return a
        'do you want to delete this dataset? confirmation page"""
        owner_org = organization_factory(
            users=[{"name": user["id"], "capacity": "admin"}]
        )
        dataset = package_factory(owner_org=owner_org["id"])

        env = {"REMOTE_USER": six.ensure_str(user["name"])}
        response = app.get(
            url_for("dataset.delete", id=dataset["name"]), extra_environ=env
        )
        assert 200 == response.status_code
        message = "Are you sure you want to delete dataset - {name}?"
        assert helpers.body_contains(response, message.format(name=dataset["title"]))

        response = app.post(
            url_for("dataset.delete", id=dataset["name"]), extra_environ=env,
            data={"cancel": ""}
        )

        assert 200 == response.status_code

    @pytest.mark.ckan_config("ckan.plugins", "test_package_controller_plugin")
    @pytest.mark.usefixtures("with_plugins")
    def test_delete(self, app, user, package, sysadmin):
        plugin = p.get_plugin("test_package_controller_plugin")
        plugin.calls.clear()
        url = url_for("dataset.delete", id=package["name"])
        app.post(url, extra_environ={"REMOTE_USER": user["name"]})
        app.post(url, extra_environ={"REMOTE_USER": sysadmin["name"]})

        assert model.Package.get(package["name"]).state == u"deleted"

        assert plugin.calls["delete"] == 2
        assert plugin.calls["after_delete"] == 2


@pytest.mark.usefixtures("clean_db", "with_request_context")
class TestResourceNew(object):
    def test_manage_dataset_resource_listing_page(self, app, user, organization_factory, package_factory, resource_factory):
        organization = organization_factory(user=user)
        dataset = package_factory(owner_org=organization["id"])
        resource = resource_factory(package_id=dataset["id"])
        env = {"REMOTE_USER": six.ensure_str(user["name"])}
        response = app.get(
            url_for("dataset.resources", id=dataset["name"]), extra_environ=env
        )
        assert resource["name"] in response
        assert resource["description"] in response
        assert resource["format"] in response

    def test_unauth_user_cannot_view_manage_dataset_resource_listing_page(
            self, app, user, organization_factory, package_factory, resource_factory
    ):
        organization = organization_factory(user=user)
        dataset = package_factory(owner_org=organization["id"])
        resource = resource_factory(package_id=dataset["id"])
        env = {"REMOTE_USER": six.ensure_str(user["name"])}
        response = app.get(
            url_for("dataset.resources", id=dataset["name"]), extra_environ=env
        )
        assert resource["name"] in response
        assert resource["description"] in response
        assert resource["format"] in response

    def test_404_on_manage_dataset_resource_listing_page_that_does_not_exist(
            self, app, user
    ):
        env = {"REMOTE_USER": six.ensure_str(user["name"])}
        response = app.get(
            url_for("dataset.resources", id="does-not-exist"),
            extra_environ=env,

        )
        assert 404 == response.status_code

    def test_add_new_resource_with_link_and_download(self, app, user, package):
        env = {"REMOTE_USER": six.ensure_str(user["name"])}
        response = app.post(
            url_for(
                "{}_resource.new".format(package["type"]), id=package["id"]
            ),
            extra_environ=env,
            data={
                "id": "",
                "url": "http://test.com/",
                "save": "go-dataset-complete"
            }
        )

        result = helpers.call_action("package_show", id=package["id"])

        response = app.get(
            url_for(
                "{}_resource.download".format(package["type"]),
                id=package["id"],
                resource_id=result["resources"][0]["id"],
            ),
            extra_environ=env,
            follow_redirects=False
        )
        assert 302 == response.status_code

    def test_editor_can_add_new_resource(self, app, user, organization_factory, package_factory):
        organization = organization_factory(
            users=[{"name": user["id"], "capacity": "editor"}]
        )
        dataset = package_factory(owner_org=organization["id"])
        env = {"REMOTE_USER": six.ensure_str(user["name"])}

        response = app.post(
            url_for(
                "{}_resource.new".format(dataset["type"]), id=dataset["id"]
            ),
            extra_environ=env,
            data={
                "id": "",
                "name": "test resource",
                "url": "http://test.com/",
                "save": "go-dataset-complete"
            }
        )
        result = helpers.call_action("package_show", id=dataset["id"])
        assert 1 == len(result["resources"])
        assert u"test resource" == result["resources"][0]["name"]

    def test_admin_can_add_new_resource(self, app, user, organization_factory, package_factory):
        organization = organization_factory(
            users=[{"name": user["id"], "capacity": "admin"}]
        )
        dataset = package_factory(owner_org=organization["id"])
        env = {"REMOTE_USER": six.ensure_str(user["name"])}

        response = app.post(
            url_for(
                "{}_resource.new".format(dataset["type"]), id=dataset["id"]
            ),
            extra_environ=env,
            data={
                "id": "",
                "name": "test resource",
                "url": "http://test.com/",
                "save": "go-dataset-complete"
            }
        )
        result = helpers.call_action("package_show", id=dataset["id"])
        assert 1 == len(result["resources"])
        assert u"test resource" == result["resources"][0]["name"]

    def test_member_cannot_add_new_resource(self, app, user, organization_factory, package_factory):
        organization = organization_factory(
            users=[{"name": user["id"], "capacity": "member"}]
        )
        dataset = package_factory(owner_org=organization["id"])
        env = {"REMOTE_USER": six.ensure_str(user["name"])}

        response = app.get(
            url_for(
                "{}_resource.new".format(dataset["type"]), id=dataset["id"]
            ),
            extra_environ=env,
            status=403,
        )

        response = app.post(
            url_for(
                "{}_resource.new".format(dataset["type"]), id=dataset["id"]
            ),
            data={"name": "test", "url": "test", "save": "save", "id": ""},
            extra_environ=env,
            status=403,
        )

    def test_non_organization_users_cannot_add_new_resource(self, app, user, organization, package_factory):
        """on an owned dataset"""
        dataset = package_factory(owner_org=organization["id"])
        env = {"REMOTE_USER": six.ensure_str(user["name"])}

        response = app.get(
            url_for(
                "{}_resource.new".format(dataset["type"]), id=dataset["id"]
            ),
            extra_environ=env,
            status=403,
        )

        response = app.post(
            url_for(
                "{}_resource.new".format(dataset["type"]), id=dataset["id"]
            ),
            data={"name": "test", "url": "test", "save": "save", "id": ""},
            extra_environ=env,
            status=403,
        )

    def test_anonymous_users_cannot_add_new_resource(self, app, organization, package_factory):
        dataset = package_factory(owner_org=organization["id"])

        response = app.get(
            url_for(
                "{}_resource.new".format(dataset["type"]), id=dataset["id"]
            ), status=403
        )

        response = app.post(
            url_for(
                "{}_resource.new".format(dataset["type"]), id=dataset["id"]
            ),
            data={"name": "test", "url": "test", "save": "save", "id": ""},
            status=403,
        )

    def test_anonymous_users_cannot_edit_resource(self, app, organization, package_factory, resource_factory):
        dataset = package_factory(owner_org=organization["id"])
        resource = resource_factory(package_id=dataset["id"])

        with app.flask_app.test_request_context():
            response = app.get(
                url_for(
                    "{}_resource.edit".format(dataset["type"]),
                    id=dataset["id"],
                    resource_id=resource["id"],
                ),
                status=403,
            )

            response = app.post(
                url_for(
                    "{}_resource.edit".format(dataset["type"]),
                    id=dataset["id"],
                    resource_id=resource["id"],
                ),
                data={"name": "test", "url": "test", "save": "save", "id": ""},
                status=403,
            )


@pytest.mark.usefixtures("clean_db", "with_plugins", "with_request_context")
class TestResourceDownload(object):

    def test_resource_download_content_type(self, create_with_upload, app, package):

        resource = create_with_upload(
            u"hello,world", u"file.csv",
            package_id=package[u"id"]
        )

        assert resource[u"mimetype"] == u"text/csv"
        url = url_for(
            u"{}_resource.download".format(package[u"type"]),
            id=package[u"id"],
            resource_id=resource[u"id"],
        )

        response = app.get(url)

        assert response.headers[u"Content-Type"] == u"text/csv"


@pytest.mark.ckan_config("ckan.plugins", "image_view")
@pytest.mark.usefixtures("clean_db", "with_plugins", "with_request_context")
class TestResourceView(object):
    def test_resource_view_create(self, app, user, organization_factory, package_factory, resource_factory):
        env = {"REMOTE_USER": six.ensure_str(user["name"])}

        owner_org = organization_factory(
            users=[{"name": user["id"], "capacity": "admin"}]
        )
        dataset = package_factory(owner_org=owner_org["id"])
        resource = resource_factory(package_id=dataset["id"])

        url = url_for(
            "resource.edit_view",
            id=resource["package_id"],
            resource_id=resource["id"],
            view_type="image_view",
        )

        response = app.post(
            url, data={"title": "Test Image View"}, extra_environ=env
        )
        assert helpers.body_contains(response, "Test Image View")

    def test_resource_view_edit(self, app, user, organization_factory, package_factory, resource_factory, resource_view_factory):
        env = {"REMOTE_USER": six.ensure_str(user["name"])}

        owner_org = organization_factory(
            users=[{"name": user["id"], "capacity": "admin"}]
        )
        dataset = package_factory(owner_org=owner_org["id"])
        resource = resource_factory(package_id=dataset["id"])

        resource_view = resource_view_factory(resource_id=resource["id"])
        url = url_for(
            "resource.edit_view",
            id=resource_view["package_id"],
            resource_id=resource_view["resource_id"],
            view_id=resource_view["id"],
        )

        response = app.post(
            url, data={"title": "Updated RV Title"}, extra_environ=env
        )
        assert helpers.body_contains(response, "Updated RV Title")

    def test_resource_view_delete(self, app, user, organization_factory, package_factory, resource_factory, resource_view_factory):
        env = {"REMOTE_USER": six.ensure_str(user["name"])}

        owner_org = organization_factory(
            users=[{"name": user["id"], "capacity": "admin"}]
        )
        dataset = package_factory(owner_org=owner_org["id"])
        resource = resource_factory(package_id=dataset["id"])

        resource_view = resource_view_factory(resource_id=resource["id"])
        url = url_for(
            "resource.edit_view",
            id=resource_view["package_id"],
            resource_id=resource_view["resource_id"],
            view_id=resource_view["id"],
        )

        response = app.post(
            url, data={"delete": "Delete"}, extra_environ=env
        )
        assert helpers.body_contains(response, "This resource has no views")

    def test_existent_resource_view_page_returns_ok_code(self, app, resource_view):

        url = url_for(
            "resource.read",
            id=resource_view["package_id"],
            resource_id=resource_view["resource_id"],
            view_id=resource_view["id"],
        )

        app.get(url, status=200)

    def test_inexistent_resource_view_page_returns_not_found_code(self, app, resource_view):

        url = url_for(
            "resource.read",
            id=resource_view["package_id"],
            resource_id=resource_view["resource_id"],
            view_id="inexistent-view-id",
        )

        app.get(url, status=404)

    def test_resource_view_description_is_rendered_as_markdown(self, app, resource_view_factory):
        resource_view = resource_view_factory(description="Some **Markdown**")
        url = url_for(
            "resource.read",
            id=resource_view["package_id"],
            resource_id=resource_view["resource_id"],
            view_id=resource_view["id"],
        )
        response = app.get(url)
        assert helpers.body_contains(response, "Some <strong>Markdown</strong>")


@pytest.mark.usefixtures("clean_db", "with_request_context")
class TestResourceRead(object):
    def test_existing_resource_with_not_associated_dataset(self, app, package, resource):
        url = url_for(
            "{}_resource.read".format(package["type"]),
            id=package["id"], resource_id=resource["id"]
        )

        app.get(url, status=404)

    def test_resource_read_logged_in_user(self, app, user, package, resource_factory):
        """
        A logged-in user can view resource page.
        """
        env = {"REMOTE_USER": six.ensure_str(user["name"])}
        resource = resource_factory(package_id=package["id"])
        url = url_for(
            "{}_resource.read".format(package["type"]),
            id=package["id"], resource_id=resource["id"]
        )

        app.get(url, status=200, extra_environ=env)

    def test_resource_read_anon_user(self, app, package, resource_factory):
        """
        An anon user can view resource page.
        """
        resource = resource_factory(package_id=package["id"])
        url = url_for(
            "{}_resource.read".format(package["type"]),
            id=package["id"], resource_id=resource["id"]
        )

        app.get(url, status=200)

    def test_resource_read_sysadmin(self, app, sysadmin, package, resource_factory):
        """
        A sysadmin can view resource page.
        """
        env = {"REMOTE_USER": six.ensure_str(sysadmin["name"])}
        resource = resource_factory(package_id=package["id"])
        url = url_for(
            "{}_resource.read".format(package["type"]),
            id=package["id"], resource_id=resource["id"]
        )

        app.get(url, status=200, extra_environ=env)

    def test_user_not_in_organization_cannot_read_private_dataset(self, app, user, organization, package_factory, resource_factory):
        env = {"REMOTE_USER": six.ensure_str(user["name"])}
        dataset = package_factory(owner_org=organization["id"], private=True)
        resource = resource_factory(package_id=dataset["id"])

        url = url_for(
            "{}_resource.read".format(dataset["type"]),
            id=dataset["id"], resource_id=resource["id"]
        )

        response = app.get(url, status=404, extra_environ=env)

    def test_organization_members_can_read_resources_in_private_datasets(
            self, app, user_factory, sysadmin_factory, organization_factory, package_factory, resource_factory
    ):
        members = {
            "member": user_factory(),
            "editor": user_factory(),
            "admin": user_factory(),
            "sysadmin": sysadmin_factory(),
        }
        organization = organization_factory(
            users=[
                {"name": members["member"]["id"], "capacity": "member"},
                {"name": members["editor"]["id"], "capacity": "editor"},
                {"name": members["admin"]["id"], "capacity": "admin"},
            ]
        )
        dataset = package_factory(owner_org=organization["id"], private=True)
        resource = resource_factory(package_id=dataset["id"])

        for user, user_dict in members.items():
            response = app.get(
                url_for(
                    "{}_resource.read".format(dataset["type"]),
                    id=dataset["name"],
                    resource_id=resource["id"],
                ),
                extra_environ={
                    "REMOTE_USER": six.ensure_str(user_dict["name"])
                },
            )
            assert "Just another test resource" in response.body

    def test_anonymous_users_cannot_read_private_datasets(self, app, organization, package_factory):
        dataset = package_factory(owner_org=organization["id"], private=True)
        response = app.get(
            url_for("dataset.read", id=dataset["name"]), status=404
        )
        assert 404 == response.status_code


@pytest.mark.usefixtures("clean_db", "with_request_context")
class TestResourceDelete(object):
    def test_dataset_owners_can_delete_resources(self, app, user, organization_factory, package_factory, resource_factory):
        owner_org = organization_factory(
            users=[{"name": user["id"], "capacity": "admin"}]
        )
        dataset = package_factory(owner_org=owner_org["id"])
        resource = resource_factory(package_id=dataset["id"])
        env = {"REMOTE_USER": six.ensure_str(user["name"])}
        response = app.post(
            url_for(
                "{}_resource.delete".format(dataset["type"]),
                id=dataset["name"],
                resource_id=resource["id"],
            ),
            extra_environ=env,
        )
        assert 200 == response.status_code
        assert helpers.body_contains(response, "This dataset has no data")

        with pytest.raises(p.toolkit.ObjectNotFound):
            helpers.call_action("resource_show", id=resource["id"])

    def test_deleting_non_existing_resource_404s(self, app, user, organization_factory, package_factory):
        owner_org = organization_factory(
            users=[{"name": user["id"], "capacity": "admin"}]
        )
        dataset = package_factory(owner_org=owner_org["id"])
        env = {"REMOTE_USER": six.ensure_str(user["name"])}
        response = app.post(
            url_for(
                "{}_resource.delete".format(dataset["type"]),
                id=dataset["name"],
                resource_id="doesnotexist",
            ),
            extra_environ=env,

        )
        assert 404 == response.status_code

    def test_anon_users_cannot_delete_owned_resources(self, app, user, organization_factory, package_factory, resource_factory):
        owner_org = organization_factory(
            users=[{"name": user["id"], "capacity": "admin"}]
        )
        dataset = package_factory(owner_org=owner_org["id"])
        resource = resource_factory(package_id=dataset["id"])

        response = app.post(
            url_for(
                "{}_resource.delete".format(dataset["type"]),
                id=dataset["name"],
                resource_id=resource["id"],
            ),
            status=403,
        )
        assert helpers.body_contains(response, "Unauthorized to delete package")

    def test_logged_in_users_cannot_delete_resources_they_do_not_own(
            self, app, user_factory, organization_factory, package_factory, resource_factory
    ):
        # setup our dataset
        owner = user_factory()
        owner_org = organization_factory(
            users=[{"name": owner["id"], "capacity": "admin"}]
        )
        dataset = package_factory(owner_org=owner_org["id"])
        resource = resource_factory(package_id=dataset["id"])

        # access as another user
        user = user_factory()
        env = {"REMOTE_USER": six.ensure_str(user["name"])}
        response = app.post(
            url_for(
                "{}_resource.delete".format(dataset["type"]),
                id=dataset["name"],
                resource_id=resource["id"],
            ),
            extra_environ=env,

        )
        assert 403 == response.status_code
        assert helpers.body_contains(response, "Unauthorized to delete package")

    def test_sysadmins_can_delete_any_resource(self, app, sysadmin, organization, package_factory, resource_factory):
        dataset = package_factory(owner_org=organization["id"])
        resource = resource_factory(package_id=dataset["id"])

        env = {"REMOTE_USER": six.ensure_str(sysadmin["name"])}
        response = app.post(
            url_for(
                "{}_resource.delete".format(dataset["type"]),
                id=dataset["name"],
                resource_id=resource["id"],
            ),
            extra_environ=env,
        )
        assert 200 == response.status_code
        assert helpers.body_contains(response, "This dataset has no data")

        with pytest.raises(p.toolkit.ObjectNotFound):
            helpers.call_action("resource_show", id=resource["id"])

    def test_confirm_and_cancel_deleting_a_resource(self, app, user, organization_factory, package_factory, resource_factory):
        """Test confirmation of deleting resources

        When resource_delete is made as a get request, it should return a
        'do you want to delete this reource? confirmation page"""
        owner_org = organization_factory(
            users=[{"name": user["id"], "capacity": "admin"}]
        )
        dataset = package_factory(owner_org=owner_org["id"])
        resource = resource_factory(package_id=dataset["id"])
        env = {"REMOTE_USER": six.ensure_str(user["name"])}
        response = app.get(
            url_for(
                "{}_resource.delete".format(dataset["type"]),
                id=dataset["name"],
                resource_id=resource["id"],
            ),
            extra_environ=env,
        )
        assert 200 == response.status_code
        message = "Are you sure you want to delete resource - {name}?"
        assert helpers.body_contains(response, message.format(name=resource["name"]))

        response = app.post(
            url_for(
                "{}_resource.delete".format(dataset["type"]),
                id=dataset["name"],
                resource_id=resource["id"],
            ),
            extra_environ=env,
            data={"cancel": ""}
        )
        assert 200 == response.status_code


@pytest.mark.usefixtures("clean_db", "clean_index", "with_request_context")
class TestSearch(object):
    def test_search_basic(self, app, package):
        offset = url_for("dataset.search")
        page = app.get(offset)

        assert helpers.body_contains(page, package["name"])

    def test_search_language_toggle(self, app, package):
        with app.flask_app.test_request_context():
            offset = url_for("dataset.search", q=package["name"])
        page = app.get(offset)

        assert helpers.body_contains(page, package["name"])
        assert helpers.body_contains(page, "q=" + package["name"])

    def test_search_sort_by_blank(self, app, package_factory):
        package_factory()

        # ?sort has caused an exception in the past
        offset = url_for("dataset.search") + "?sort"
        app.get(offset)

    def test_search_sort_by_bad(self, app, package_factory):
        package_factory()

        # bad spiders try all sorts of invalid values for sort. They should get
        # a 400 error with specific error message. No need to alert the
        # administrator.
        offset = url_for("dataset.search") + "?sort=gvgyr_fgevat+nfp"
        response = app.get(offset)
        if response.status == 200:
            import sys

            sys.stdout.write(response.body)
            raise Exception(
                "Solr returned an unknown error message. "
                "Please check the error handling "
                "in ckan/lib/search/query.py:run"
            )

    def test_search_solr_syntax_error(self, app, package_factory):
        package_factory()

        # SOLR raises SyntaxError when it can't parse q (or other fields?).
        # Whilst this could be due to a bad user input, it could also be
        # because CKAN mangled things somehow and therefore we flag it up to
        # the administrator and give a meaningless error, just in case
        offset = url_for("dataset.search") + "?q=--included"
        search_response = app.get(offset)

        search_response_html = BeautifulSoup(search_response.data)
        err_msg = search_response_html.select("#search-error")
        err_msg = "".join([n.text for n in err_msg])
        assert "error while searching" in err_msg

    def test_search_plugin_hooks(self, app):
        with p.use_plugin("test_package_controller_plugin") as plugin:

            offset = url_for("dataset.search")
            app.get(offset)

            # get redirected ...
            assert plugin.calls["before_search"] == 1, plugin.calls
            assert plugin.calls["after_search"] == 1, plugin.calls

    def test_search_page_request(self, app, package_factory):
        """Requesting package search page returns list of datasets."""

        package_factory(name="dataset-one", title="Dataset One")
        package_factory(name="dataset-two", title="Dataset Two")
        package_factory(name="dataset-three", title="Dataset Three")

        search_url = url_for("dataset.search")
        search_response = app.get(search_url)

        assert "3 datasets found" in search_response

        search_response_html = BeautifulSoup(search_response.data)
        ds_titles = search_response_html.select(
            ".dataset-list " ".dataset-item " ".dataset-heading a"
        )
        ds_titles = [n.string for n in ds_titles]

        assert len(ds_titles) == 3
        assert "Dataset One" in ds_titles
        assert "Dataset Two" in ds_titles
        assert "Dataset Three" in ds_titles

    def test_search_page_results(self, app, package_factory):
        """Searching for datasets returns expected results."""

        package_factory(name="dataset-one", title="Dataset One")
        package_factory(name="dataset-two", title="Dataset Two")
        package_factory(name="dataset-three", title="Dataset Three")

        search_url = url_for("dataset.search")
        search_results = app.get(search_url, query_string={'q': 'One'})

        assert "1 dataset found" in search_results

        search_response_html = BeautifulSoup(search_results.data)
        ds_titles = search_response_html.select(
            ".dataset-list " ".dataset-item " ".dataset-heading a"
        )
        ds_titles = [n.string for n in ds_titles]

        assert len(ds_titles) == 1
        assert "Dataset One" in ds_titles

    @pytest.mark.ckan_config('ckan.datasets_per_page', 1)
    def test_repeatable_params(self, app, package_factory):
        """Searching for datasets returns expected results."""

        package_factory(name="dataset-one", title="Test Dataset One")
        package_factory(name="dataset-two", title="Test Dataset Two")

        search_url = url_for("dataset.search", title=['Test', 'Dataset'])
        search_results = app.get(search_url)
        html = BeautifulSoup(search_results.data)
        links = html.select('.pagination a')
        # first, second and "Next" pages
        assert len(links) == 3

        params = [set(urlparse(a['href']).query.split('&')) for a in links]
        for group in params:
            assert 'title=Test' in group
            assert 'title=Dataset' in group

    def test_search_page_no_results(self, app, package_factory):
        """Search with non-returning phrase returns no results."""

        package_factory(name="dataset-one", title="Dataset One")
        package_factory(name="dataset-two", title="Dataset Two")
        package_factory(name="dataset-three", title="Dataset Three")

        search_url = url_for("dataset.search")
        search_results = app.get(search_url, query_string={'q': 'Nout'})

        assert 'No datasets found for "Nout"' in search_results

        search_response_html = BeautifulSoup(search_results.data)
        ds_titles = search_response_html.select(
            ".dataset-list " ".dataset-item " ".dataset-heading a"
        )
        ds_titles = [n.string for n in ds_titles]

        assert len(ds_titles) == 0

    def test_search_page_results_tag(self, app, package_factory):
        """Searching with a tag returns expected results."""

        package_factory(
            name="dataset-one", title="Dataset One", tags=[{"name": "my-tag"}]
        )
        package_factory(name="dataset-two", title="Dataset Two")
        package_factory(name="dataset-three", title="Dataset Three")

        search_url = url_for("dataset.search")
        search_response = app.get(search_url)
        assert "/dataset/?tags=my-tag" in search_response

        tag_search_response = app.get("/dataset?tags=my-tag")

        assert "1 dataset found" in tag_search_response

        search_response_html = BeautifulSoup(tag_search_response.data)
        ds_titles = search_response_html.select(
            ".dataset-list " ".dataset-item " ".dataset-heading a"
        )
        ds_titles = [n.string for n in ds_titles]

        assert len(ds_titles) == 1
        assert "Dataset One" in ds_titles

    def test_search_page_results_tags(self, app, package_factory):
        """Searching with a tag returns expected results with multiple tags"""

        package_factory(
            name="dataset-one",
            title="Dataset One",
            tags=[
                {"name": "my-tag-1"},
                {"name": "my-tag-2"},
                {"name": "my-tag-3"},
            ],
        )
        package_factory(name="dataset-two", title="Dataset Two")
        package_factory(name="dataset-three", title="Dataset Three")

        params = "/dataset/?tags=my-tag-1&tags=my-tag-2&tags=my-tag-3"
        tag_search_response = app.get(params)

        assert "1 dataset found" in tag_search_response

        search_response_html = BeautifulSoup(tag_search_response.data)
        ds_titles = search_response_html.select(".filtered")
        assert len(ds_titles) == 3

    def test_search_page_results_private(self, app, package_factory, organization):
        """Private datasets don't show up in dataset search results."""
        package_factory(
            name="dataset-one",
            title="Dataset One",
            owner_org=organization["id"],
            private=True,
        )
        package_factory(name="dataset-two", title="Dataset Two")
        package_factory(name="dataset-three", title="Dataset Three")

        search_url = url_for("dataset.search")
        search_response = app.get(search_url)

        search_response_html = BeautifulSoup(search_response.data)
        ds_titles = search_response_html.select(
            ".dataset-list " ".dataset-item " ".dataset-heading a"
        )
        ds_titles = [n.string for n in ds_titles]

        assert len(ds_titles) == 2
        assert "Dataset One" not in ds_titles
        assert "Dataset Two" in ds_titles
        assert "Dataset Three" in ds_titles

    def test_user_not_in_organization_cannot_search_private_datasets(
            self, app, user, organization, package_factory
    ):
        dataset = package_factory(owner_org=organization["id"], private=True)
        env = {"REMOTE_USER": six.ensure_str(user["name"])}
        search_url = url_for("dataset.search")
        search_response = app.get(search_url, extra_environ=env)

        search_response_html = BeautifulSoup(search_response.data)
        ds_titles = search_response_html.select(
            ".dataset-list " ".dataset-item " ".dataset-heading a"
        )
        assert [n.string for n in ds_titles] == []

    def test_user_in_organization_can_search_private_datasets(self, app, user, organization_factory, package_factory):

        organization = organization_factory(
            users=[{"name": user["id"], "capacity": "member"}]
        )
        dataset = package_factory(
            title="A private dataset",
            owner_org=organization["id"],
            private=True,
        )
        env = {"REMOTE_USER": six.ensure_str(user["name"])}
        search_url = url_for("dataset.search")
        search_response = app.get(search_url, extra_environ=env)

        search_response_html = BeautifulSoup(search_response.data)
        ds_titles = search_response_html.select(
            ".dataset-list " ".dataset-item " ".dataset-heading a"
        )
        assert [n.string for n in ds_titles] == ["A private dataset"]

    def test_user_in_different_organization_cannot_search_private_datasets(
            self, app, user, organization_factory, package_factory
    ):
        org1 = organization_factory(
            users=[{"name": user["id"], "capacity": "member"}]
        )
        org2 = organization_factory()
        dataset = package_factory(
            title="A private dataset", owner_org=org2["id"], private=True
        )
        env = {"REMOTE_USER": six.ensure_str(user["name"])}
        search_url = url_for("dataset.search")
        search_response = app.get(search_url, extra_environ=env)

        search_response_html = BeautifulSoup(search_response.data)
        ds_titles = search_response_html.select(
            ".dataset-list " ".dataset-item " ".dataset-heading a"
        )
        assert [n.string for n in ds_titles] == []

    @pytest.mark.ckan_config("ckan.search.default_include_private", "false")
    def test_search_default_include_private_false(self, app, user, organization_factory, package_factory):
        organization = organization_factory(
            users=[{"name": user["id"], "capacity": "member"}]
        )
        dataset = package_factory(owner_org=organization["id"], private=True)
        env = {"REMOTE_USER": six.ensure_str(user["name"])}
        search_url = url_for("dataset.search")
        search_response = app.get(search_url, extra_environ=env)

        search_response_html = BeautifulSoup(search_response.data)
        ds_titles = search_response_html.select(
            ".dataset-list " ".dataset-item " ".dataset-heading a"
        )
        assert [n.string for n in ds_titles] == []

    def test_sysadmin_can_search_private_datasets(self, app, sysadmin, organization, package_factory):
        dataset = package_factory(
            title="A private dataset",
            owner_org=organization["id"],
            private=True,
        )
        env = {"REMOTE_USER": six.ensure_str(sysadmin["name"])}
        search_url = url_for("dataset.search")
        search_response = app.get(search_url, extra_environ=env)

        search_response_html = BeautifulSoup(search_response.data)
        ds_titles = search_response_html.select(
            ".dataset-list " ".dataset-item " ".dataset-heading a"
        )
        assert [n.string for n in ds_titles] == ["A private dataset"]

    def test_search_with_extra_params(self, app, monkeypatch):
        url = url_for('dataset.search')
        url += '?ext_a=1&ext_a=2&ext_b=3'
        search_result = {
            'count': 0,
            'sort': "score desc, metadata_modified desc",
            'facets': {},
            'search_facets': {},
            'results': []
        }
        search = mock.Mock(return_value=search_result)
        logic._actions['package_search'] = search
        app.get(url)
        search.assert_called()
        extras = search.call_args[0][1]['extras']
        assert extras == {'ext_a': ['1', '2'], 'ext_b': '3'}


@pytest.mark.usefixtures("clean_db", "with_request_context")
class TestPackageFollow(object):
    def test_package_follow(self, app, user, package):

        env = {"REMOTE_USER": six.ensure_str(user["name"])}
        follow_url = url_for("dataset.follow", id=package["id"])
        response = app.post(follow_url, extra_environ=env)
        assert "You are now following {0}".format(package["title"]) in response

    def test_package_follow_not_exist(self, app, user):
        """Pass an id for a package that doesn't exist"""


        env = {"REMOTE_USER": six.ensure_str(user["name"])}
        follow_url = url_for("dataset.follow", id="not-here")
        response = app.post(follow_url, extra_environ=env)

        assert "Dataset not found" in response

    def test_package_unfollow(self, app, user, package):

        env = {"REMOTE_USER": six.ensure_str(user["name"])}
        follow_url = url_for("dataset.follow", id=package["id"])
        app.post(follow_url, extra_environ=env)

        unfollow_url = url_for("dataset.unfollow", id=package["id"])
        unfollow_response = app.post(
            unfollow_url, extra_environ=env
        )

        assert (
            "You are no longer following {0}".format(package["title"])
            in unfollow_response
        )

    def test_package_unfollow_not_following(self, app, user, package):
        """Unfollow a package not currently following"""

        env = {"REMOTE_USER": six.ensure_str(user["name"])}
        unfollow_url = url_for("dataset.unfollow", id=package["id"])
        unfollow_response = app.post(
            unfollow_url, extra_environ=env
        )

        assert (
            "You are not following {0}".format(package["id"])
            in unfollow_response
        )

    def test_package_unfollow_not_exist(self, app, user):
        """Unfollow a package that doesn't exist."""


        env = {"REMOTE_USER": six.ensure_str(user["name"])}
        unfollow_url = url_for("dataset.unfollow", id="not-here")
        unfollow_response = app.post(
            unfollow_url, extra_environ=env
        )
        assert "Dataset not found" in unfollow_response

    def test_package_follower_list(self, app, package, sysadmin):
        """Following users appear on followers list page."""

        env = {"REMOTE_USER": six.ensure_str(sysadmin["name"])}
        follow_url = url_for("dataset.follow", id=package["id"])
        app.post(follow_url, extra_environ=env)

        followers_url = url_for("dataset.followers", id=package["id"])

        # Only sysadmins can view the followers list pages
        followers_response = app.get(
            followers_url, extra_environ=env, status=200
        )
        assert sysadmin["display_name"] in followers_response


@pytest.mark.usefixtures("clean_db", "with_request_context")
class TestDatasetRead(object):
    def test_dataset_read(self, app, package):

        url = url_for("dataset.read", id=package["name"])
        response = app.get(url)
        assert package["title"] in response

    def test_redirect_when_given_id(self, app, package):
        response = app.get(
            url_for("dataset.read", id=package["id"]),
            follow_redirects=False
        )
        # redirect replaces the ID with the name in the URL
        expected_url = url_for("dataset.read", id=package["name"], _external=True)
        assert response.headers['location'] == expected_url

    def test_redirect_also_with_activity_parameter(self, app, user, sysadmin, package_factory):
        dataset = package_factory(user=user)
        activity = activity_model.package_activity_list(
            dataset["id"], limit=1, offset=0
        )[0]
        # view as an admin because viewing the old versions of a dataset
        env = {"REMOTE_USER": six.ensure_str(sysadmin["name"])}
        response = app.get(
            url_for("dataset.read", id=dataset["id"], activity_id=activity.id),
            status=302,
            extra_environ=env,
            follow_redirects=False
        )
        expected_path = url_for("dataset.read", id=dataset["name"], _external=True, activity_id=activity.id)
        assert response.headers['location'] == expected_path

    def test_no_redirect_loop_when_name_is_the_same_as_the_id(self, app, package_factory):
        dataset = package_factory(id="abc", name="abc")
        app.get(
            url_for("dataset.read", id=dataset["id"]), status=200
        )  # ie no redirect


@pytest.mark.usefixtures("clean_db", "with_request_context")
class TestActivity(object):
    def test_simple(self, app, user, package_factory):
        """Checking the template shows the activity stream."""
        dataset = package_factory(user=user)

        url = url_for("dataset.activity", id=dataset["id"])
        response = app.get(url)
        assert "Mr. Test User" in response
        assert "created the dataset" in response

    def test_create_dataset(self, app, user, package_factory):

        dataset = package_factory(user=user)

        url = url_for("dataset.activity", id=dataset["id"])
        response = app.get(url)
        assert (
            '<a href="/user/{}">Mr. Test User'.format(user["name"]) in response
        )
        assert "created the dataset" in response
        assert (
            '<a href="/dataset/{}">Test Dataset'.format(dataset["id"])
            in response
        )

    def _clear_activities(self):
        model.Session.query(model.Activity).delete()
        model.Session.flush()

    def test_change_dataset(self, app, user, package_factory):

        dataset = package_factory(user=user)
        self._clear_activities()
        dataset["title"] = "Dataset with changed title"
        helpers.call_action(
            "package_update", context={"user": user["name"]}, **dataset
        )

        url = url_for("dataset.activity", id=dataset["id"])
        response = app.get(url)
        assert (
            '<a href="/user/{}">Mr. Test User'.format(user["name"]) in response
        )
        assert "updated the dataset" in response
        assert (
            '<a href="/dataset/{}">Dataset with changed title'.format(
                dataset["id"]
            )
            in response
        )

    def test_create_tag_directly(self, app, user, package_factory):

        dataset = package_factory(user=user)
        self._clear_activities()
        dataset["tags"] = [{"name": "some_tag"}]
        helpers.call_action(
            "package_update", context={"user": user["name"]}, **dataset
        )

        url = url_for("dataset.activity", id=dataset["id"])
        response = app.get(url)
        assert (
            '<a href="/user/{}">Mr. Test User'.format(user["name"]) in response
        )
        assert "updated the dataset" in response
        assert (
            '<a href="/dataset/{}">{}'.format(dataset["id"], dataset["title"])
            in response
        )

        activities = helpers.call_action(
            "package_activity_list", id=dataset["id"]
        )

        assert len(activities) == 1

    def test_create_tag(self, app, user, package_factory):
        dataset = package_factory(user=user)
        self._clear_activities()
        dataset["tags"] = [{"name": "some_tag"}]
        helpers.call_action(
            "package_update", context={"user": user["name"]}, **dataset
        )

        url = url_for("dataset.activity", id=dataset["id"])
        response = app.get(url)
        assert (
            '<a href="/user/{}">Mr. Test User'.format(user["name"]) in response
        )
        assert "updated the dataset" in response
        assert (
            '<a href="/dataset/{}">{}'.format(dataset["id"], dataset["title"])
            in response
        )

        activities = helpers.call_action(
            "package_activity_list", id=dataset["id"]
        )

        assert len(activities) == 1

    def test_create_extra(self, app, user, package_factory):
        dataset = package_factory(user=user)
        self._clear_activities()
        dataset["extras"] = [{"key": "some", "value": "extra"}]
        helpers.call_action(
            "package_update", context={"user": user["name"]}, **dataset
        )

        url = url_for("dataset.activity", id=dataset["id"])
        response = app.get(url)
        assert (
            '<a href="/user/{}">Mr. Test User'.format(user["name"]) in response
        )
        assert "updated the dataset" in response
        assert (
            '<a href="/dataset/{}">{}'.format(dataset["id"], dataset["title"])
            in response
        )

        activities = helpers.call_action(
            "package_activity_list", id=dataset["id"]
        )

        assert len(activities) == 1

    def test_create_resource(self, app, user, package_factory):
        dataset = package_factory(user=user)
        self._clear_activities()
        helpers.call_action(
            "resource_create",
            context={"user": user["name"]},
            name="Test resource",
            package_id=dataset["id"],
        )

        url = url_for("dataset.activity", id=dataset["id"])
        response = app.get(url)
        assert (
            '<a href="/user/{}">Mr. Test User'.format(user["name"]) in response
        )
        assert "updated the dataset" in response
        assert (
            '<a href="/dataset/{}">{}'.format(dataset["id"], dataset["title"])
            in response
        )

        activities = helpers.call_action(
            "package_activity_list", id=dataset["id"]
        )

        assert len(activities) == 1

    def test_update_resource(self, app, user, package_factory, resource_factory):
        dataset = package_factory(user=user)
        resource = resource_factory(package_id=dataset["id"])
        self._clear_activities()

        helpers.call_action(
            "resource_update",
            context={"user": user["name"]},
            id=resource["id"],
            name="Test resource updated",
            package_id=dataset["id"],
        )

        url = url_for("dataset.activity", id=dataset["id"])
        response = app.get(url)
        assert (
            '<a href="/user/{}">Mr. Test User'.format(user["name"]) in response
        )
        assert "updated the dataset" in response
        assert (
            '<a href="/dataset/{}">{}'.format(dataset["id"], dataset["title"])
            in response
        )

        activities = helpers.call_action(
            "package_activity_list", id=dataset["id"]
        )

        assert len(activities) == 1

    def test_delete_dataset(self, app, user, organization, package_factory):
        dataset = package_factory(owner_org=organization["id"], user=user)
        self._clear_activities()
        helpers.call_action(
            "package_delete", context={"user": user["name"]}, **dataset
        )

        url = url_for("organization.activity", id=organization["id"])
        response = app.get(url)
        assert (
            '<a href="/user/{}">Mr. Test User'.format(user["name"]) in response
        )
        assert "deleted the dataset" in response
        assert (
            '<a href="/dataset/{}">Test Dataset'.format(dataset["id"])
            in response
        )

    def test_admin_can_see_old_versions(self, app, user, package_factory):

        env = {"REMOTE_USER": six.ensure_str(user["name"])}
        dataset = package_factory(user=user)

        url = url_for("dataset.activity", id=dataset["id"])
        response = app.get(url, extra_environ=env)
        assert "View this version" in response

    def test_public_cant_see_old_versions(self, app, user, package_factory):

        dataset = package_factory(user=user)

        url = url_for("dataset.activity", id=dataset["id"])
        response = app.get(url)
        assert "View this version" not in response

    def test_admin_can_see_changes(self, app, user, package):

        env = {"REMOTE_USER": six.ensure_str(user["name"])}
        package["title"] = "Changed"
        helpers.call_action("package_update", **package)

        url = url_for("dataset.activity", id=package["id"])
        response = app.get(url, extra_environ=env)
        assert "Changes" in response

    def test_public_cant_see_changes(self, app, package):
        package["title"] = "Changed"
        helpers.call_action("package_update", **package)

        url = url_for("dataset.activity", id=package["id"])
        response = app.get(url)
        assert "Changes" not in response

    def test_legacy_changed_package_activity(self, app, user, package_factory):
        """Render an activity that was created with an earlier version of CKAN,
        and it has not been migrated (with migrate_package_activity.py)
        """

        dataset = package_factory(user=user)

        # delete the modern Activity object that's been automatically created
        modern_activity = (
            model.Session.query(model.Activity)
            .filter_by(object_id=dataset["id"])
            .one()
        )
        modern_activity.delete()

        # Create an Activity object as it was in earlier versions of CKAN.
        # This code is based on:
        # https://github.com/ckan/ckan/blob/b348bf2fe68db6704ea0a3e22d533ded3d8d4344/ckan/model/package.py#L508
        activity_type = "changed"
        dataset_table_dict = dictization.table_dictize(
            model.Package.get(dataset["id"]), context={"model": model}
        )
        activity = model.Activity(
            user_id=user["id"],
            object_id=dataset["id"],
            activity_type="%s package" % activity_type,
            data={
                # "actor": a legacy activity had no "actor"
                # "package": a legacy activity had just the package table,
                # rather than the result of package_show
                "package": dataset_table_dict
            },
        )
        model.Session.add(activity)
        # a legacy activity had a ActivityDetail associated with the Activity
        # This code is based on:
        # https://github.com/ckan/ckan/blob/b348bf2fe68db6704ea0a3e22d533ded3d8d4344/ckan/model/package.py#L542
        activity_detail = model.ActivityDetail(
            activity_id=activity.id,
            object_id=dataset["id"],
            object_type=u"Package",
            activity_type=activity_type,
            data={u"package": dataset_table_dict},
        )
        model.Session.add(activity_detail)
        model.Session.flush()

        url = url_for("dataset.activity", id=dataset["id"])
        response = app.get(url)
        assert (
            '<a href="/user/{}">Mr. Test User'.format(user["name"]) in response
        )
        assert "updated the dataset" in response
        assert (
            '<a href="/dataset/{}">Test Dataset'.format(dataset["id"])
            in response
        )

    # ckanext-canada uses their IActivity to add their custom activity to the
    # list of validators: https://github.com/open-data/ckanext-canada/blob/6870e5bc38a04aa8cef191b5e9eb361f9560872b/ckanext/canada/plugins.py#L596
    # but it's easier here to just hack patch it in
    @mock.patch(
        "ckan.logic.validators.object_id_validators",
        dict(
            list(object_id_validators.items())
            + [("changed datastore", package_id_exists)]
        ),
    )
    def test_custom_activity(self, app, user, organization_factory, package_factory, resource_factory):
        """Render a custom activity
        """

        organization = organization_factory(
            users=[{"name": user["id"], "capacity": "admin"}]
        )
        dataset = package_factory(owner_org=organization["id"], user=user)
        resource = resource_factory(package_id=dataset["id"])
        self._clear_activities()

        # Create a custom Activity object. This one is inspired by:
        # https://github.com/open-data/ckanext-canada/blob/master/ckanext/canada/activity.py
        activity_dict = {
            "user_id": user["id"],
            "object_id": dataset["id"],
            "activity_type": "changed datastore",
            "data": {
                "resource_id": resource["id"],
                "pkg_type": dataset["type"],
                "resource_name": "june-2018",
                "owner_org": organization["name"],
                "count": 5,
            },
        }
        helpers.call_action("activity_create", **activity_dict)

        url = url_for("dataset.activity", id=dataset["id"])
        response = app.get(url)
        assert (
            '<a href="/user/{}">Mr. Test User'.format(user["name"]) in response
        )
        # it renders the activity with fallback.html, since we've not defined
        # changed_datastore.html in this case
        assert "changed datastore" in response


@pytest.mark.usefixtures("clean_db", "with_request_context")
class TestChanges(object):  # i.e. the diff
    def test_simple(self, app, user, package_factory):
        dataset = package_factory(title="First title", user=user)
        dataset["title"] = "Second title"
        helpers.call_action("package_update", **dataset)

        activity = activity_model.package_activity_list(
            dataset["id"], limit=1, offset=0
        )[0]
        env = {"REMOTE_USER": six.ensure_str(user["name"])}
        response = app.get(
            url_for("dataset.changes", id=activity.id), extra_environ=env
        )
        assert helpers.body_contains(response, "First")
        assert helpers.body_contains(response, "Second")


@pytest.mark.usefixtures('clean_db', 'with_request_context')
class TestCollaborators(object):

    def test_collaborators_tab_not_shown(self, app, sysadmin, package):
        env = {'REMOTE_USER': six.ensure_str(sysadmin['name'])}
        response = app.get(url=url_for('dataset.edit', id=package['name']), extra_environ=env)
        assert 'Collaborators' not in response

        # Route not registered
        with pytest.raises(BuildError):
            url = url_for('dataset.collaborators_read', id=package['name'])
        app.get(
            '/dataset/collaborators/{}'.format(package['name']), extra_environ=env, status=404)

    @pytest.mark.ckan_config('ckan.auth.allow_dataset_collaborators', 'true')
    def test_collaborators_tab_shown(self, app, sysadmin, package):
        env = {'REMOTE_USER': six.ensure_str(sysadmin['name'])}
        response = app.get(url=url_for('dataset.edit', id=package['name']), extra_environ=env)
        assert 'Collaborators' in response

        # Route registered
        url = url_for('dataset.collaborators_read', id=package['name'])
        app.get(url, extra_environ=env)

    @pytest.mark.ckan_config('ckan.auth.allow_dataset_collaborators', 'true')
    def test_collaborators_no_admins_by_default(self, app, sysadmin, package):
        env = {'REMOTE_USER': six.ensure_str(sysadmin['name'])}
        url = url_for('dataset.new_collaborator', id=package['name'])
        response = app.get(url, extra_environ=env)

        assert '<option value="admin">' not in response

    @pytest.mark.ckan_config('ckan.auth.allow_dataset_collaborators', 'true')
    @pytest.mark.ckan_config('ckan.auth.allow_admin_collaborators', 'true')
    def test_collaborators_admins_enabled(self, app, sysadmin, package):
        env = {'REMOTE_USER': six.ensure_str(sysadmin['name'])}
        url = url_for('dataset.new_collaborator', id=package['name'])
        response = app.get(url, extra_environ=env)

        assert '<option value="admin">' in response


@pytest.mark.usefixtures('clean_db')
class TestResourceListing(object):
    def test_resource_listing_premissions_sysadmin(self, app, package_factory, sysadmin, organization):
        pkg = package_factory(owner_org=organization["id"])
        app.get(
            url_for("dataset.resources", id=pkg["name"]),
            extra_environ={"REMOTE_USER": sysadmin["name"]}, status=200)

    def test_resource_listing_premissions_auth_user(self, app, user, organization_factory, package_factory):
        org = organization_factory(user=user)
        pkg = package_factory(owner_org=org["id"])

        app.get(
            url_for("dataset.resources", id=pkg["name"]),
            extra_environ={"REMOTE_USER": user["name"]}, status=200)

    def test_resource_listing_premissions_non_auth_user(self, app, organization, package_factory):
        pkg = package_factory(owner_org=organization["id"])
        app.get(
            url_for("dataset.resources", id=pkg["name"]),
            extra_environ={"REMOTE_USER": "someone_else"}, status=403)

    def test_resource_listing_premissions_not_logged_in(self, app, package):
        app.get(url_for("dataset.resources", id=package["name"]), status=403)


@pytest.mark.usefixtures('clean_db')
class TestNonActivePackages:
    def test_read(self, app, package_factory):
        pkg = package_factory(state="deleted")
        url = url_for("dataset.read", id=pkg["name"])
        app.get(url, status=404)

    def test_read_as_admin(self, app, package_factory, sysadmin):
        pkg = package_factory(state="deleted")
        url = url_for("dataset.read", id=pkg["name"])
        res = app.get(
            url, status=200, extra_environ={"REMOTE_USER": sysadmin["name"]}
        )


@pytest.mark.usefixtures("clean_db", "clean_index")
class TestReadOnly(object):
    def test_read_nonexistentpackage(self, app):
        name = "anonexistentpackage"
        url = url_for("dataset.read", id=name)
        app.get(url, status=404)

    def test_read_internal_links(self, app, package_factory):
        pkg = package_factory(
            notes="Decoy link here: decoy:decoy, real links here: dataset:pkg-1, "
            "tag:tag_1 group:test-group-1 and a multi-word tag: tag:\"multi word with punctuation.\"",)
        res = app.get(url_for("dataset.read", id=pkg["name"]))
        page = BeautifulSoup(res.data)
        link = page.body.find("a", text="dataset:pkg-1")
        assert link
        assert link["href"] == "/dataset/pkg-1"

        link = page.body.find("a", text="group:test-group-1")
        assert link
        assert link["href"] == "/group/test-group-1"
        assert "decoy</a>" not in res, res
        assert 'decoy"' not in res, res

    @pytest.mark.ckan_config("ckan.plugins", "test_package_controller_plugin")
    @pytest.mark.usefixtures("with_plugins")
    def test_read_plugin_hook(self, app, package):
        plugin = p.get_plugin("test_package_controller_plugin")
        plugin.calls.clear()
        app.get(url_for("dataset.read", id=package["name"]))
        assert plugin.calls["read"] == 1
        assert plugin.calls["after_show"] == 1
