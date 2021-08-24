# encoding: utf-8

import datetime
import copy
from pprint import pformat

import pytest

from ckan.lib.create_test_data import CreateTestData
from ckan import model
from ckan.logic.schema import (
    default_create_package_schema,
    default_update_package_schema,
    default_group_schema,
    default_tags_schema,
)
from ckan.lib.navl.dictization_functions import validate
from ckan.lib.dictization import model_dictize, model_save
from ckan.lib.dictization.model_dictize import package_dictize, group_dictize


@pytest.mark.usefixtures("clean_db", "clean_index", "with_request_context")
class TestGroupListDictize:
    def test_group_list_dictize(self, group):
        group_list = model.Session.query(model.Group).filter_by().all()
        context = {"model": model, "session": model.Session}

        group_dicts = model_dictize.group_list_dictize(group_list, context)

        assert len(group_dicts) == 1
        assert group_dicts[0]["name"] == group["name"]
        assert group_dicts[0]["package_count"] == 0
        assert "extras" not in group_dicts[0]
        assert "tags" not in group_dicts[0]
        assert "groups" not in group_dicts[0]

    def test_group_list_dictize_sorted(self, group_factory):
        group_factory(name="aa")
        group_factory(name="bb")
        group_list = [model.Group.get(u"bb"), model.Group.get(u"aa")]
        context = {"model": model, "session": model.Session}

        group_dicts = model_dictize.group_list_dictize(group_list, context)

        # list is resorted by name
        assert group_dicts[0]["name"] == "aa"
        assert group_dicts[1]["name"] == "bb"

    def test_group_list_dictize_reverse_sorted(self, group_factory):
        group_factory(name="aa")
        group_factory(name="bb")
        group_list = [model.Group.get(u"aa"), model.Group.get(u"bb")]
        context = {"model": model, "session": model.Session}

        group_dicts = model_dictize.group_list_dictize(
            group_list, context, reverse=True
        )

        assert group_dicts[0]["name"] == "bb"
        assert group_dicts[1]["name"] == "aa"

    def test_group_list_dictize_sort_by_package_count(self, group_factory, package_factory):
        group_factory(name="aa")
        group_factory(name="bb")
        package_factory(groups=[{"name": "aa"}, {"name": "bb"}])
        package_factory(groups=[{"name": "bb"}])
        group_list = [model.Group.get(u"bb"), model.Group.get(u"aa")]
        context = {"model": model, "session": model.Session}

        group_dicts = model_dictize.group_list_dictize(
            group_list,
            context,
            sort_key=lambda x: x["package_count"],
            with_package_counts=True,
        )

        # list is resorted by package counts
        assert group_dicts[0]["name"] == "aa"
        assert group_dicts[1]["name"] == "bb"

    def test_group_list_dictize_without_package_count(self, package_factory, group):
        package_factory(groups=[{"name": group["name"]}])
        group_list = [model.Group.get(group["name"])]
        context = {"model": model, "session": model.Session}

        group_dicts = model_dictize.group_list_dictize(
            group_list, context, with_package_counts=False
        )

        assert "packages" not in group_dicts[0]

    def test_group_list_dictize_including_extras(self, group_factory):
        group_factory(extras=[{"key": "k1", "value": "v1"}])
        group_list = model.Session.query(model.Group).filter_by().all()
        context = {"model": model, "session": model.Session}

        group_dicts = model_dictize.group_list_dictize(
            group_list, context, include_extras=True
        )

        assert group_dicts[0]["extras"][0]["key"] == "k1"

    def test_group_list_dictize_including_tags(self, group_factory):
        group_factory()
        # group tags aren't in the group_create schema, so its slightly more
        # convoluted way to create them
        group_obj = model.Session.query(model.Group).first()
        tag = model.Tag(name="t1")
        model.Session.add(tag)
        model.Session.commit()
        tag = model.Session.query(model.Tag).first()
        group_obj = model.Session.query(model.Group).first()
        member = model.Member(
            group=group_obj, table_id=tag.id, table_name="tag"
        )
        model.Session.add(member)
        model.Session.commit()
        group_list = model.Session.query(model.Group).filter_by().all()
        context = {"model": model, "session": model.Session}

        group_dicts = model_dictize.group_list_dictize(
            group_list, context, include_tags=True
        )

        assert group_dicts[0]["tags"][0]["name"] == "t1"

    def test_group_list_dictize_including_groups(self, group_factory):
        group_factory(name="parent")
        group_factory(name="child", groups=[{"name": "parent"}])
        group_list = [model.Group.get(u"parent"), model.Group.get(u"child")]
        context = {"model": model, "session": model.Session}

        child_dict, parent_dict = model_dictize.group_list_dictize(
            group_list, context, include_groups=True
        )

        assert parent_dict["name"] == "parent"
        assert child_dict["name"] == "child"
        assert parent_dict["groups"] == []
        assert child_dict["groups"][0]["name"] == "parent"


@pytest.mark.usefixtures("clean_db", "clean_index", "with_request_context")
class TestGroupDictize:
    def test_group_dictize(self, group_factory):
        group = group_factory(name="test_dictize")
        group_obj = model.Session.query(model.Group).filter_by().first()
        context = {"model": model, "session": model.Session}

        group = model_dictize.group_dictize(group_obj, context)

        assert group["name"] == "test_dictize"
        assert group["packages"] == []
        assert group["extras"] == []
        assert group["tags"] == []
        assert group["groups"] == []

    def test_group_dictize_group_with_dataset(self, package_factory, group):
        package = package_factory(groups=[{"name": group["name"]}])
        group_obj = model.Session.query(model.Group).filter_by().first()
        context = {"model": model, "session": model.Session}

        group = model_dictize.group_dictize(group_obj, context)

        assert group["packages"][0]["name"] == package["name"]
        assert group["packages"][0]["groups"][0]["name"] == group["name"]

    def test_group_dictize_group_with_extra(self, group_factory):
        group_factory(extras=[{"key": "k1", "value": "v1"}])
        group_obj = model.Session.query(model.Group).filter_by().first()
        context = {"model": model, "session": model.Session}

        group = model_dictize.group_dictize(group_obj, context)

        assert group["extras"][0]["key"] == "k1"

    def test_group_dictize_group_with_parent_group(self, group_factory):
        group_factory(name="parent")
        group_factory(name="child", groups=[{"name": "parent"}])
        group_obj = model.Group.get("child")
        context = {"model": model, "session": model.Session}

        group = model_dictize.group_dictize(group_obj, context)

        assert len(group["groups"]) == 1
        assert group["groups"][0]["name"] == "parent"
        assert group["groups"][0]["package_count"] == 0

    def test_group_dictize_without_packages(self, group_factory):
        # group_list_dictize might not be interested in packages at all
        # so sets these options. e.g. it is not all_fields nor are the results
        # sorted by the number of packages.
        group_factory()
        group_obj = model.Session.query(model.Group).filter_by().first()
        context = {"model": model, "session": model.Session}

        group = model_dictize.group_dictize(
            group_obj, context, packages_field=None
        )

        assert "packages" not in group

    def test_group_dictize_with_package_list(self, package_factory, group):
        package = package_factory(groups=[{"name": group["name"]}])
        group_obj = model.Session.query(model.Group).filter_by().first()
        context = {"model": model, "session": model.Session}

        group = model_dictize.group_dictize(group_obj, context)

        assert type(group["packages"]) == list
        assert len(group["packages"]) == 1
        assert group["packages"][0]["name"] == package["name"]

    def test_group_dictize_with_package_list_limited(self, package_factory, group):
        """
        Packages returned in group are limited by context var.
        """
        for _ in range(10):
            package_factory(groups=[{"name": group["name"]}])
        group_obj = model.Session.query(model.Group).filter_by().first()
        # limit packages to 4
        context = {
            "model": model,
            "session": model.Session,
            "limits": {"packages": 4},
        }

        group = model_dictize.group_dictize(group_obj, context)

        assert len(group["packages"]) == 4

    def test_group_dictize_with_package_list_limited_over(self, package_factory, group):
        """
        Packages limit is set higher than number of packages in group.
        """
        for _ in range(3):
            package_factory(groups=[{"name": group["name"]}])
        group_obj = model.Session.query(model.Group).filter_by().first()
        # limit packages to 4
        context = {
            "model": model,
            "session": model.Session,
            "limits": {"packages": 4},
        }

        group = model_dictize.group_dictize(group_obj, context)

        assert len(group["packages"]) == 3

    @pytest.mark.ckan_config("ckan.search.rows_max", "4")
    def test_group_dictize_with_package_list_limited_by_config(self, package_factory, group):
        for _ in range(5):
            package_factory(groups=[{"name": group["name"]}])
        group_obj = model.Session.query(model.Group).filter_by().first()
        context = {"model": model, "session": model.Session}

        group = model_dictize.group_dictize(group_obj, context)

        assert len(group["packages"]) == 4
        # limited by ckan.search.rows_max

    def test_group_dictize_with_package_count(self, package_factory, group, group_factory):
        # group_list_dictize calls it like this by default
        other_group_ = group_factory()
        package_factory(groups=[{"name": group["name"]}])
        package_factory(groups=[{"name": other_group_["name"]}])
        group_obj = model.Session.query(model.Group).filter_by().first()
        context = {
            "model": model,
            "session": model.Session,
            "dataset_counts": model_dictize.get_group_dataset_counts(),
        }

        group = model_dictize.group_dictize(
            group_obj, context, packages_field="dataset_count"
        )
        assert group["package_count"] == 1

    def test_group_dictize_with_no_packages_field_but_still_package_count(
            self, package_factory, group,
    ):
        # logic.get.group_show calls it like this when not include_datasets
        package_factory(groups=[{"name": group["name"]}])
        group_obj = model.Session.query(model.Group).filter_by().first()
        context = {"model": model, "session": model.Session}
        # not supplying dataset_counts in this case either

        group = model_dictize.group_dictize(
            group_obj, context, packages_field="dataset_count"
        )

        assert "packages" not in group
        assert group["package_count"] == 1

    def test_group_dictize_for_org_with_package_list(self, package_factory, organization):
        package = package_factory(owner_org=organization["id"])
        group_obj = model.Session.query(model.Group).filter_by().first()
        context = {"model": model, "session": model.Session}

        org = model_dictize.group_dictize(group_obj, context)

        assert type(org["packages"]) == list
        assert len(org["packages"]) == 1
        assert org["packages"][0]["name"] == package["name"]

    def test_group_dictize_for_org_with_package_count(self, organization_factory, package_factory):
        # group_list_dictize calls it like this by default
        org_ = organization_factory()
        other_org_ = organization_factory()
        package_factory(owner_org=org_["id"])
        package_factory(owner_org=other_org_["id"])
        org_obj = model.Session.query(model.Group).filter_by().first()
        context = {
            "model": model,
            "session": model.Session,
            "dataset_counts": model_dictize.get_group_dataset_counts(),
        }

        org = model_dictize.group_dictize(
            org_obj, context, packages_field="dataset_count"
        )

        assert org["package_count"] == 1


@pytest.mark.usefixtures("clean_db", "with_request_context")
class TestPackageDictize:
    def remove_changable_values(self, dict_):
        dict_ = copy.deepcopy(dict_)
        for key, value in list(dict_.items()):
            if key.endswith("id") and key != "license_id":
                dict_.pop(key)
            if key == "created":
                dict_.pop(key)
            if "timestamp" in key:
                dict_.pop(key)
            if key in ["metadata_created", "metadata_modified"]:
                dict_.pop(key)
            if isinstance(value, list):
                for i, sub_dict in enumerate(value):
                    value[i] = self.remove_changable_values(sub_dict)
        return dict_

    def assert_equals_expected(self, expected_dict, result_dict):
        result_dict = self.remove_changable_values(result_dict)
        superfluous_keys = set(result_dict) - set(expected_dict)
        assert not superfluous_keys, "Did not expect key: %s" % " ".join(
            ("%s=%s" % (k, result_dict[k]) for k in superfluous_keys)
        )
        for key in expected_dict:
            assert (
                expected_dict[key] == result_dict[key]
            ), "%s=%s should be %s" % (
                key,
                result_dict[key],
                expected_dict[key],
            )

    def test_package_dictize_basic(self, package_factory):
        dataset = package_factory(
            name="test_dataset_dictize",
            notes="Some *description*",
            url="http://example.com",
        )
        dataset_obj = model.Package.get(dataset["id"])
        context = {"model": model, "session": model.Session}

        result = model_dictize.package_dictize(dataset_obj, context)

        assert result["name"] == dataset["name"]
        assert not (result["isopen"])
        assert result["type"] == dataset["type"]
        today = datetime.date.today().strftime("%Y-%m-%d")
        assert result["metadata_modified"].startswith(today)
        assert result["metadata_created"].startswith(today)
        assert result["creator_user_id"] == dataset_obj.creator_user_id
        expected_dict = {
            "author": None,
            "author_email": None,
            "extras": [],
            "groups": [],
            "isopen": False,
            "license_id": None,
            "license_title": None,
            "maintainer": None,
            "maintainer_email": None,
            "name": u"test_dataset_dictize",
            "notes": "Some *description*",
            "num_resources": 0,
            "num_tags": 0,
            "organization": None,
            "owner_org": None,
            "private": False,
            "relationships_as_object": [],
            "relationships_as_subject": [],
            "resources": [],
            "state": u"active",
            "tags": [],
            "title": u"Test Dataset",
            "type": u"dataset",
            "url": "http://example.com",
            "version": None,
        }
        self.assert_equals_expected(expected_dict, result)

    def test_package_dictize_license(self, package_factory):
        dataset = package_factory(license_id="cc-by")
        dataset_obj = model.Package.get(dataset["id"])
        context = {"model": model, "session": model.Session}

        result = model_dictize.package_dictize(dataset_obj, context)

        assert result["isopen"]
        assert result["license_id"] == "cc-by"
        assert (
            result["license_url"]
            == "http://www.opendefinition.org/licenses/cc-by"
        )
        assert result["license_title"] == "Creative Commons Attribution"

    def test_package_dictize_title_stripped_of_whitespace(self, package_factory):
        dataset = package_factory(title=" has whitespace \t")
        dataset_obj = model.Package.get(dataset["id"])
        context = {"model": model, "session": model.Session}

        result = model_dictize.package_dictize(dataset_obj, context)

        assert result["title"] == "has whitespace"
        assert dataset_obj.title == " has whitespace \t"

    def test_package_dictize_resource(self, resource_factory, package):
        resource = resource_factory(
            package_id=package["id"], name="test_pkg_dictize"
        )
        dataset_obj = model.Package.get(package["id"])
        context = {"model": model, "session": model.Session}

        result = model_dictize.package_dictize(dataset_obj, context)

        assert_equal_for_keys(result["resources"][0], resource, "name", "url")
        expected_dict = {
            u"cache_last_updated": None,
            u"cache_url": None,
            u"description": u"Just another test resource.",
            u"format": u"res_format",
            u"hash": u"",
            u"last_modified": None,
            u"mimetype": None,
            u"mimetype_inner": None,
            u"name": u"test_pkg_dictize",
            u"position": 0,
            u"resource_type": None,
            u"size": None,
            u"state": u"active",
            u"url": u"http://link.to.some.data",
            u"url_type": None,
        }
        self.assert_equals_expected(expected_dict, result["resources"][0])

    def test_package_dictize_resource_upload_and_striped(self, resource_factory, package):
        resource = resource_factory(
            package=package["id"],
            name="test_pkg_dictize",
            url_type="upload",
            url="some_filename.csv",
        )

        context = {"model": model, "session": model.Session}

        result = model_save.resource_dict_save(resource, context)

        expected_dict = {u"url": u"some_filename.csv", u"url_type": u"upload"}
        assert expected_dict["url"] == result.url

    def test_package_dictize_resource_upload_with_url_and_striped(self, resource_factory, package):
        resource = resource_factory(
            package=package["id"],
            name="test_pkg_dictize",
            url_type="upload",
            url="http://some_filename.csv",
        )

        context = {"model": model, "session": model.Session}

        result = model_save.resource_dict_save(resource, context)

        expected_dict = {u"url": u"some_filename.csv", u"url_type": u"upload"}
        assert expected_dict["url"] == result.url

    def test_package_dictize_tags(self, package_factory):
        dataset = package_factory(tags=[{"name": "fish"}])
        dataset_obj = model.Package.get(dataset["id"])
        context = {"model": model, "session": model.Session}

        result = model_dictize.package_dictize(dataset_obj, context)

        assert result["tags"][0]["name"] == "fish"
        expected_dict = {
            "display_name": u"fish",
            u"name": u"fish",
            u"state": u"active",
        }
        self.assert_equals_expected(expected_dict, result["tags"][0])

    def test_package_dictize_extras(self, package_factory):
        extras_dict = {"key": "latitude", "value": "54.6"}
        dataset = package_factory(extras=[extras_dict])
        dataset_obj = model.Package.get(dataset["id"])
        context = {"model": model, "session": model.Session}

        result = model_dictize.package_dictize(dataset_obj, context)

        assert_equal_for_keys(result["extras"][0], extras_dict, "key", "value")
        expected_dict = {
            u"key": u"latitude",
            u"state": u"active",
            u"value": u"54.6",
        }
        self.assert_equals_expected(expected_dict, result["extras"][0])

    def test_package_dictize_group(self, group_factory, package_factory):
        group = group_factory(
            name="test_group_dictize", title="Test Group Dictize"
        )
        dataset = package_factory(groups=[{"name": group["name"]}])
        dataset_obj = model.Package.get(dataset["id"])
        context = {"model": model, "session": model.Session}

        result = model_dictize.package_dictize(dataset_obj, context)

        assert_equal_for_keys(result["groups"][0], group, "name")
        expected_dict = {
            u"approval_status": u"approved",
            u"capacity": u"public",
            u"description": u"A test description for this test group.",
            "display_name": u"Test Group Dictize",
            "image_display_url": u"",
            u"image_url": u"",
            u"is_organization": False,
            u"name": u"test_group_dictize",
            u"state": u"active",
            u"title": u"Test Group Dictize",
            u"type": u"group",
        }
        self.assert_equals_expected(expected_dict, result["groups"][0])

    def test_package_dictize_owner_org(self, organization_factory, package_factory):
        org = organization_factory(name="test_package_dictize")
        dataset = package_factory(owner_org=org["id"])
        dataset_obj = model.Package.get(dataset["id"])
        context = {"model": model, "session": model.Session}

        result = model_dictize.package_dictize(dataset_obj, context)

        assert result["owner_org"] == org["id"]
        assert_equal_for_keys(result["organization"], org, "name")
        expected_dict = {
            u"approval_status": u"approved",
            u"description": u"Just another test organization.",
            u"image_url": u"https://placekitten.com/g/200/100",
            u"is_organization": True,
            u"name": u"test_package_dictize",
            u"state": u"active",
            u"title": u"Test Organization",
            u"type": u"organization",
        }
        self.assert_equals_expected(expected_dict, result["organization"])


def assert_equal_for_keys(dict1, dict2, *keys):
    for key in keys:
        assert key in dict1, 'Dict 1 misses key "%s"' % key
        assert key in dict2, 'Dict 2 misses key "%s"' % key
        assert dict1[key] == dict2[key], "%s != %s (key=%s)" % (
            dict1[key],
            dict2[key],
            key,
        )


@pytest.mark.usefixtures("clean_db")
class TestTagDictize(object):
    """Unit tests for the tag_dictize() function."""

    def test_tag_dictize_including_datasets(self, package_factory):
        """By default a dictized tag should include the tag's datasets."""
        # Make a dataset in order to have a tag created.
        package_factory(tags=[dict(name="test_tag")])
        tag = model.Tag.get("test_tag")

        tag_dict = model_dictize.tag_dictize(tag, context={"model": model})

        assert len(tag_dict["packages"]) == 1

    def test_tag_dictize_not_including_datasets(self, package_factory):
        """include_datasets=False should exclude datasets from tag dicts."""
        # Make a dataset in order to have a tag created.
        package_factory(tags=[dict(name="test_tag")])
        tag = model.Tag.get("test_tag")

        tag_dict = model_dictize.tag_dictize(
            tag, context={"model": model}, include_datasets=False
        )

        assert not tag_dict.get("packages")


class TestVocabularyDictize(object):
    """Unit tests for the vocabulary_dictize() function."""

    def test_vocabulary_dictize_including_datasets(self, vocabulary_factory, package_factory):
        """include_datasets=True should include datasets in vocab dicts."""
        vocab_dict = vocabulary_factory(
            tags=[dict(name="test_tag_1"), dict(name="test_tag_2")]
        )
        package_factory(tags=vocab_dict["tags"])
        vocab_obj = model.Vocabulary.get(vocab_dict["name"])

        vocab_dict = model_dictize.vocabulary_dictize(
            vocab_obj, context={"model": model}, include_datasets=True
        )

        assert len(vocab_dict["tags"]) == 2
        for tag in vocab_dict["tags"]:
            assert len(tag["packages"]) == 1

    def test_vocabulary_dictize_not_including_datasets(self, vocabulary_factory, package_factory):
        """By default datasets should not be included in vocab dicts."""
        vocab_dict = vocabulary_factory(
            tags=[dict(name="test_tag_1"), dict(name="test_tag_2")]
        )
        package_factory(tags=vocab_dict["tags"])
        vocab_obj = model.Vocabulary.get(vocab_dict["name"])

        vocab_dict = model_dictize.vocabulary_dictize(
            vocab_obj, context={"model": model}
        )

        assert len(vocab_dict["tags"]) == 2
        for tag in vocab_dict["tags"]:
            assert len(tag.get("packages", [])) == 0


@pytest.mark.usefixtures("clean_db", "with_request_context")
class TestActivityDictize(object):
    def test_include_data(self, package, user, activity_factory):
        activity = activity_factory(
            user_id=user["id"],
            object_id=package["id"],
            activity_type="new package",
            data={"package": copy.deepcopy(package), "actor": "Mr Someone"},
        )
        activity_obj = model.Activity.get(activity["id"])
        context = {"model": model, "session": model.Session}
        dictized = model_dictize.activity_dictize(
            activity_obj, context, include_data=True
        )
        assert dictized["user_id"] == user["id"]
        assert dictized["activity_type"] == "new package"
        assert dictized["data"]["package"]["title"] == package["title"]
        assert dictized["data"]["package"]["id"] == package["id"]
        assert dictized["data"]["actor"] == "Mr Someone"

    def test_dont_include_data(self, package, user, activity_factory):
        activity = activity_factory(
            user_id=user["id"],
            object_id=package["id"],
            activity_type="new package",
            data={"package": copy.deepcopy(package), "actor": "Mr Someone"},
        )
        activity_obj = model.Activity.get(activity["id"])
        context = {"model": model, "session": model.Session}
        dictized = model_dictize.activity_dictize(
            activity_obj, context, include_data=False
        )
        assert dictized["user_id"] == user["id"]
        assert dictized["activity_type"] == "new package"
        assert dictized["data"] == {"package": {"title": package["title"]}}


@pytest.mark.usefixtures("clean_db")
class TestPackageSchema(object):
    def remove_changable_columns(self, dict):
        for key, value in list(dict.items()):
            if key.endswith("id") and key != "license_id":
                dict.pop(key)
            if key in ("created", "metadata_modified"):
                dict.pop(key)

            if isinstance(value, list):
                for new_dict in value:
                    self.remove_changable_columns(new_dict)
        return dict

    def test_package_schema(self):
        CreateTestData.create()
        context = {"model": model, "session": model.Session}
        pkg = (
            model.Session.query(model.Package)
            .filter_by(name="annakarenina")
            .first()
        )

        package_id = pkg.id
        result = package_dictize(pkg, context)
        self.remove_changable_columns(result)

        result["name"] = "anna2"
        # we need to remove these as they have been added
        del result["relationships_as_object"]
        del result["relationships_as_subject"]

        converted_data, errors = validate(
            result, default_create_package_schema(), context
        )

        expected_data = {
            "extras": [
                {"key": u"genre", "value": u"romantic novel"},
                {"key": u"original media", "value": u"book"},
            ],
            "groups": [
                {u"name": u"david", u"title": u"Dave's books"},
                {u"name": u"roger", u"title": u"Roger's books"},
            ],
            "license_id": u"other-open",
            "name": u"anna2",
            "type": u"dataset",
            "notes": u"Some test notes\n\n### A 3rd level heading\n\n**Some bolded text.**\n\n*Some italicized text.*\n\nForeign characters:\nu with umlaut \xfc\n66-style quote \u201c\nforeign word: th\xfcmb\n\nNeeds escaping:\nleft arrow <\n\n<http://ckan.net/>\n\n",
            "private": False,
            "resources": [
                {
                    "alt_url": u"alt123",
                    "description": u'Full text. Needs escaping: " Umlaut: \xfc',
                    "format": u"plain text",
                    "hash": u"abc123",
                    "size_extra": u"123",
                    "url": u"http://datahub.io/download/x=1&y=2",
                },
                {
                    "alt_url": u"alt345",
                    "description": u"Index of the novel",
                    "format": u"JSON",
                    "hash": u"def456",
                    "size_extra": u"345",
                    "url": u"http://datahub.io/index.json",
                },
            ],
            "tags": [
                {"name": u"Flexible \u30a1"},
                {"name": u"russian"},
                {"name": u"tolstoy"},
            ],
            "title": u"A Novel By Tolstoy",
            "url": u"http://datahub.io",
            "version": u"0.7a",
        }

        assert converted_data == expected_data, pformat(converted_data)
        assert not errors, errors

        data = converted_data
        data["name"] = u"annakarenina"
        data.pop("title")
        data["resources"][0]["url"] = "fsdfafasfsaf"
        data["resources"][1].pop("url")

        converted_data, errors = validate(
            data, default_create_package_schema(), context
        )

        assert errors == {"name": [u"That URL is already in use."]}, pformat(
            errors
        )

        data["id"] = package_id
        data["name"] = "????jfaiofjioafjij"

        converted_data, errors = validate(
            data, default_update_package_schema(), context
        )
        assert errors == {
            "name": [
                u"Must be purely lowercase alphanumeric (ascii) "
                "characters and these symbols: -_"
            ]
        }, pformat(errors)

    @pytest.mark.usefixtures("clean_index")
    def test_group_schema(self):
        CreateTestData.create()
        context = {"model": model, "session": model.Session}
        group = model.Session.query(model.Group).first()
        data = group_dictize(group, context)

        # we don't want these here
        del data["groups"]
        del data["users"]
        del data["tags"]
        del data["extras"]

        converted_data, errors = validate(
            data, default_group_schema(), context
        )
        assert not errors
        group_pack = sorted(group.packages(), key=lambda x: x.id)

        converted_data["packages"] = sorted(
            converted_data["packages"], key=lambda x: x["id"]
        )

        expected = {
            "description": u"These are books that David likes.",
            "id": group.id,
            "name": u"david",
            "is_organization": False,
            "type": u"group",
            "image_url": u"",
            "image_display_url": u"",
            "packages": sorted(
                [
                    {
                        "id": group_pack[0].id,
                        "name": group_pack[0].name,
                        "title": group_pack[0].title,
                    },
                    {
                        "id": group_pack[1].id,
                        "name": group_pack[1].name,
                        "title": group_pack[1].title,
                    },
                ],
                key=lambda x: x["id"],
            ),
            "title": u"Dave's books",
            "approval_status": u"approved",
        }

        assert converted_data == expected, pformat(converted_data)

        data["packages"].sort(key=lambda x: x["id"])
        data["packages"][0]["id"] = "fjdlksajfalsf"
        data["packages"][1].pop("id")
        data["packages"][1].pop("name")

        converted_data, errors = validate(
            data, default_group_schema(), context
        )
        assert errors == {
            "packages": [
                {"id": [u"Not found: Dataset"]},
                {"id": [u"Missing value"]},
            ]
        }, pformat(errors)


class TestTagSchema:
    def test_tag_schema_allows_spaces(self):
        """Asserts that a tag name with space is valid"""
        ignored = ""
        context = {"model": model, "session": model.Session}
        data = {
            "name": u"with space",
            "revision_timestamp": ignored,
            "state": ignored,
        }
        _, errors = validate(data, default_tags_schema(), context)
        assert not errors, str(errors)

    def test_tag_schema_allows_limited_punctuation(self):
        """Asserts that a tag name with limited punctuation is valid"""
        ignored = ""
        context = {"model": model, "session": model.Session}
        data = {
            "name": u".-_",
            "revision_timestamp": ignored,
            "state": ignored,
        }
        _, errors = validate(data, default_tags_schema(), context)
        assert not errors, str(errors)

    def test_tag_schema_allows_capital_letters(self):
        """Asserts that tag names can have capital letters"""
        ignored = ""
        context = {"model": model, "session": model.Session}
        data = {
            "name": u"CAPITALS",
            "revision_timestamp": ignored,
            "state": ignored,
        }
        _, errors = validate(data, default_tags_schema(), context)
        assert not errors, str(errors)

    def test_tag_schema_disallows_most_punctuation(self):
        """Asserts most punctuation is disallowed"""
        not_allowed = r'!?"\'+=:;@#~[]{}()*&^%$,'
        context = {"model": model, "session": model.Session}
        ignored = ""
        data = {"revision_timestamp": ignored, "state": ignored}
        for ch in not_allowed:
            data["name"] = "Character " + ch
            _, errors = validate(data, default_tags_schema(), context)
            assert errors
            assert "name" in errors
            error_message = errors["name"][0]
            assert data["name"] in error_message, error_message
            assert "can only contain alphanumeric characters" in error_message

    def test_tag_schema_disallows_whitespace_other_than_spaces(self):
        """Asserts whitespace characters, such as tabs, are not allowed."""
        not_allowed = "\t\n\r\f\v"
        context = {"model": model, "session": model.Session}
        ignored = ""
        data = {"revision_timestamp": ignored, "state": ignored}
        for ch in not_allowed:
            data["name"] = "Bad " + ch + " character"
            _, errors = validate(data, default_tags_schema(), context)
            assert errors, repr(ch)
            assert "name" in errors
            error_message = errors["name"][0]
            assert data["name"] in error_message, error_message
            assert "can only contain alphanumeric characters" in error_message
