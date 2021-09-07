# encoding: utf-8
"""
NB Don't test logic functions here. This is just for the mechanics of the API
controller itself.
"""
import json
import re

import pytest
import six
from io import BytesIO
from ckan.lib.helpers import url_for
import ckan.tests.helpers as helpers
from ckan.lib import uploader as ckan_uploader


@pytest.mark.parametrize(
    "ver, expected, status",
    [(0, 1, 404), (1, 1, 200), (2, 2, 200), (3, 3, 200), (4, 1, 404)],
)
def test_get_api_version(ver, expected, status, app):
    resp = app.get(url_for("api.get_api", ver=str(ver)), status=status)
    if status == 200:
        assert resp.json["version"] == expected


def test_readonly_is_get_able_with_normal_url_params(app):
    """Test that a read-only action is GET-able

    Picks an action within `get.py` and checks that it works if it's
    invoked with a http GET request.  The action's data_dict is
    populated from the url parameters.
    """
    params = {"q": "russian"}
    resp = app.get(
        url_for("api.action", logic_function="package_search", ver=3),
        params=params,
        status=200,
    )


def test_sideeffect_action_is_not_get_able(app):
    """Test that a non-readonly action is not GET-able.

    Picks an action outside of `get.py`, and checks that it 400s if an
    attempt to invoke with a http GET request is made.
    """
    data_dict = {"type": "dataset", "name": "a-name"}
    resp = app.get(
        url_for("api.action", logic_function="package_create", ver=3),
        json=data_dict,
        status=400,
    )
    msg = (
        "Bad request - JSON Error: Invalid request."
        " Please use POST method for your request"
    )
    assert msg in resp


@pytest.mark.usefixtures("clean_db", "with_request_context")
class TestApiController(object):
    def test_resource_create_upload_file(
            self, app, monkeypatch, tmpdir, ckan_config, user, package_factory
    ):
        monkeypatch.setitem(ckan_config, u"ckan.storage_path", str(tmpdir))
        monkeypatch.setattr(ckan_uploader, u"_storage_path", str(tmpdir))

        pkg = package_factory(creator_user_id=user["id"])

        url = url_for(
            "api.action",
            logic_function="resource_create",
            ver=3,
        )
        env = {"REMOTE_USER": six.ensure_str(user["name"])}

        content = six.ensure_binary('upload-content')
        upload_content = BytesIO(content)
        postparams = {
            "name": "test-flask-upload",
            "package_id": pkg["id"],
            "upload": (upload_content, "test-upload.txt"),
        }

        resp = app.post(
            url,
            data=postparams,
            environ_overrides=env,
            content_type="multipart/form-data",
        )
        result = resp.json["result"]
        assert "upload" == result["url_type"]
        assert len(content) == result["size"]

    def test_unicode_in_error_message_works_ok(self, app):
        # Use tag_delete to echo back some unicode

        org_url = "/api/action/tag_delete"
        data_dict = {"id": u"Delta symbol: \u0394"}  # unicode gets rec'd ok
        response = app.post(url=org_url, data=data_dict, status=404)
        # The unicode is backslash encoded (because that is the default when
        # you do str(exception) )
        assert helpers.body_contains(response, "Delta symbol: \\u0394")

    @pytest.mark.usefixtures("clean_index")
    def test_dataset_autocomplete_name(self, app, package_factory):
        dataset = package_factory(name="rivers")
        url = url_for("api.dataset_autocomplete", ver=2)
        assert url == "/api/2/util/dataset/autocomplete"

        response = app.get(
            url=url, query_string={"incomplete": u"rive"}, status=200
        )

        results = json.loads(response.body)
        assert results == {
            u"ResultSet": {
                u"Result": [
                    {
                        u"match_field": u"name",
                        u"name": u"rivers",
                        u"match_displayed": u"rivers",
                        u"title": dataset["title"],
                    }
                ]
            }
        }
        assert (
            response.headers["Content-Type"]
            == "application/json;charset=utf-8"
        )

    @pytest.mark.usefixtures("clean_index")
    def test_dataset_autocomplete_title(self, app, package_factory):
        dataset = package_factory(name="test_ri", title="Rivers")
        url = url_for("api.dataset_autocomplete", ver=2)
        assert url == "/api/2/util/dataset/autocomplete"

        response = app.get(
            url=url, query_string={"incomplete": u"riv"}, status=200
        )

        results = json.loads(response.body)
        assert results == {
            u"ResultSet": {
                u"Result": [
                    {
                        u"match_field": u"title",
                        u"name": dataset["name"],
                        u"match_displayed": u"Rivers (test_ri)",
                        u"title": u"Rivers",
                    }
                ]
            }
        }
        assert (
            response.headers["Content-Type"]
            == "application/json;charset=utf-8"
        )

    def test_tag_autocomplete(self, app, package_factory):
        package_factory(tags=[{"name": "rivers ア"}])
        url = url_for("api.tag_autocomplete", ver=2)

        assert url == "/api/2/util/tag/autocomplete"

        response = app.get(
            url=url, query_string={"incomplete": u"rs ア"}, status=200
        )

        assert response.json == {
            "ResultSet": {"Result": [{"Name": "rivers ア"}]}
        }
        assert (
            response.headers["Content-Type"]
            == "application/json;charset=utf-8"
        )

    def test_group_autocomplete_by_name(self, app, group_factory):
        org = group_factory(name="rivers", title="Bridges")
        url = url_for("api.group_autocomplete", ver=2)
        assert url == "/api/2/util/group/autocomplete"

        response = app.get(url=url, query_string={"q": u"rive"}, status=200)

        results = json.loads(response.body)
        assert len(results) == 1
        assert results[0]["name"] == "rivers"
        assert results[0]["title"] == "Bridges"
        assert (
            response.headers["Content-Type"]
            == "application/json;charset=utf-8"
        )

    def test_group_autocomplete_by_title(self, app, group_factory):
        org = group_factory(name="frogs", title="Bugs")
        url = url_for("api.group_autocomplete", ver=2)

        response = app.get(url=url, query_string={"q": u"bug"}, status=200)

        results = json.loads(response.body)
        assert len(results) == 1
        assert results[0]["name"] == "frogs"

    def test_organization_autocomplete_by_name(self, app, organization_factory):
        org = organization_factory(name="simple-dummy-org")
        url = url_for("api.organization_autocomplete", ver=2)
        assert url == "/api/2/util/organization/autocomplete"

        response = app.get(url=url, query_string={"q": u"simple"}, status=200)

        results = json.loads(response.body)
        assert len(results) == 1
        assert results[0]["name"] == "simple-dummy-org"
        assert results[0]["title"] == org["title"]
        assert (
            response.headers["Content-Type"]
            == "application/json;charset=utf-8"
        )

    def test_organization_autocomplete_by_title(self, app, organization_factory):
        org = organization_factory(title="Simple dummy org")
        url = url_for("api.organization_autocomplete", ver=2)

        response = app.get(
            url=url, query_string={"q": u"simple dum"}, status=200
        )

        results = json.loads(response.body)
        assert len(results) == 1
        assert results[0]["title"] == "Simple dummy org"

    def test_config_option_list_access_sysadmin(self, app, sysadmin):
        url = url_for(
            "api.action",
            logic_function="config_option_list",
            ver=3,
        )

        app.get(
            url=url,
            query_string={},
            environ_overrides={"REMOTE_USER": six.ensure_str(sysadmin["name"])},
            status=200,
        )

    def test_config_option_list_access_sysadmin_jsonp(self, app, sysadmin):
        url = url_for(
            "api.action",
            logic_function="config_option_list",
            ver=3,
        )

        app.get(
            url=url,
            query_string={"callback": "myfn"},
            environ_overrides={"REMOTE_USER": six.ensure_str(sysadmin["name"])},
            status=403,
        )

    def test_jsonp_works_on_get_requests(self, app, package_factory):

        dataset1 = package_factory()
        dataset2 = package_factory()

        url = url_for(
            "api.action",
            logic_function="package_list",
            ver=3,
        )

        res = app.get(url=url, query_string={"callback": "my_callback"})
        assert re.match(r"my_callback\(.*\);", six.ensure_str(res.body)), res
        # Unwrap JSONP callback (we want to look at the data).
        start = len("my_callback") + 1
        msg = res.body[start:-2]
        res_dict = json.loads(msg)
        assert res_dict["success"]
        assert sorted(res_dict["result"]) == sorted(
            [dataset1["name"], dataset2["name"]]
        )

    def test_jsonp_returns_javascript_content_type(self, app):
        url = url_for(
            "api.action",
            logic_function="status_show",
            ver=3,
        )

        res = app.get(url=url, query_string={"callback": "my_callback"})
        assert "application/javascript" in res.headers.get("Content-Type")

    def test_jsonp_does_not_work_on_post_requests(self, app, package_factory):

        dataset1 = package_factory()
        dataset2 = package_factory()

        url = url_for(
            "api.action",
            logic_function="package_list",
            ver=3,
            callback="my_callback",
        )

        res = app.post(url=url)
        # The callback param is ignored and the normal response is returned
        assert not six.ensure_str(res.body).startswith("my_callback")
        res_dict = json.loads(res.body)
        assert res_dict["success"]
        assert sorted(res_dict["result"]) == sorted(
            [dataset1["name"], dataset2["name"]]
        )

    @pytest.mark.parametrize(
        "incomplete, expected",
        [
            (None, set()),
            ("", set()),
            ("cs", {"csv"}),
            ("on", {"json"}),
            ("s", {"csv", "json"}),
            ("xls", set()),
        ],
    )
    def test_format_autocomplete(self, incomplete, expected, app, resource_factory):
        resource_factory(format="CSV")
        resource_factory(format="JSON")

        resp = app.get(
            url_for("api.format_autocomplete", ver=2, incomplete=incomplete)
        )
        result = {res["Format"] for res in resp.json["ResultSet"]["Result"]}
        assert result == expected
