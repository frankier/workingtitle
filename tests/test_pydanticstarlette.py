import asyncio

import pytest
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from starlette.datastructures import QueryParams
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import PlainTextResponse

from workingtitle.pydanticstarlette import (
    FileStem,
    LenientInt,
    OptionalPositiveInt,
    ParamError,
    PositiveInt,
    Sorters,
    collect_query_params,
    int_or,
    json_list_of,
    lenient_int,
    parse_query,
    query_params,
    require_found,
)


def make_request(query_string):
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [],
            "query_string": query_string.encode(),
        }
    )


def call(handler, query_string):
    return asyncio.run(handler(make_request(query_string)))


class TestLenientInt:
    def test_parses(self):
        assert lenient_int("12") == 12

    def test_unparseable_falls_back_to_none(self):
        assert lenient_int("x") is None
        assert lenient_int(None) is None


class PositiveModel(BaseModel):
    page: PositiveInt = 1
    experiment: OptionalPositiveInt = None


class TestPositiveInt:
    def test_defaults_and_values(self):
        assert PositiveModel().page == 1
        assert PositiveModel(page="7").page == 7
        assert PositiveModel(experiment="3").experiment == 3

    @pytest.mark.parametrize("value", ["0", "-1", "x", "1.5", "1 or 1=1"])
    def test_rejects_non_positive_or_unparseable(self, value):
        with pytest.raises(ValidationError):
            PositiveModel(page=value)

    def test_optional_absent_is_none(self):
        assert PositiveModel(experiment=None).experiment is None

    def test_optional_present_is_strict(self):
        with pytest.raises(ValidationError):
            PositiveModel(experiment="x")


class TestIntOr:
    def test_accepts_sentinel_and_int(self):
        Step = int_or("all")

        class M(BaseModel):
            step: Step = "all"

        assert M().step == "all"
        assert M(step="all").step == "all"
        assert M(step="5").step == 5

    def test_rejects_other_strings(self):
        Step = int_or("all")

        class M(BaseModel):
            step: Step = "all"

        with pytest.raises(ValidationError):
            M(step="x")


class TestJsonListOf:
    def test_parses_json_list(self):
        Names = json_list_of(str, message="must be a JSON list of names")

        class M(BaseModel):
            channels: Names | None = None

        assert M(channels='["a", "b"]').channels == ["a", "b"]

    @pytest.mark.parametrize("value", ["not json", '"a"', "[1]", "null"])
    def test_rejects_non_list_of_strings(self, value):
        Names = json_list_of(str, message="must be a JSON list of names")

        class M(BaseModel):
            channels: Names | None = None

        with pytest.raises(ValidationError) as excinfo:
            M(channels=value)
        assert "must be a JSON list of names" in str(excinfo.value)


class TestFileStem:
    def test_accepts_plain_names(self):
        class M(BaseModel):
            name: FileStem

        assert M(name="1003P_epochs.set").name == "1003P_epochs.set"

    @pytest.mark.parametrize(
        "value", ["", ".", "..", "../x", "a/b", "a\\b", "/etc/passwd"]
    )
    def test_rejects_paths(self, value):
        class M(BaseModel):
            name: FileStem

        with pytest.raises(ValidationError):
            M(name=value)


class TestCollectQueryParams:
    def test_accepts_plain_dicts(self):
        assert collect_query_params({"a": "1"}) == {"a": "1"}

    def test_scalars_and_indexed_groups(self):
        query = QueryParams(
            "a=1&b=2&sort[1][dir]=desc&sort[0][field]=id&sort[0][dir]=asc"
        )
        assert collect_query_params(query) == {
            "a": "1",
            "b": "2",
            "sort": [
                {"field": "id", "dir": "asc"},
                {"dir": "desc"},
            ],
        }

    def test_malformed_indexed_key_is_rejected(self):
        with pytest.raises(ParamError):
            collect_query_params(QueryParams("sort[0]=x"))

    def test_repeated_indexed_part_is_rejected(self):
        with pytest.raises(ParamError):
            collect_query_params(QueryParams("sort[0][dir]=asc&sort[0][dir]=desc"))


class SortModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    sorters: Sorters = Field(default_factory=list, validation_alias="sort")


class TestSorters:
    def test_parses_tabulator_sorts(self):
        params = parse_query(
            QueryParams("sort[0][field]=id&sort[0][dir]=desc"), SortModel
        )
        assert params.sorters == [("id", "desc")]

    def test_default_is_empty(self):
        assert parse_query(QueryParams(""), SortModel).sorters == []

    def test_incomplete_sorter_is_rejected(self):
        with pytest.raises(ValidationError):
            parse_query(QueryParams("sort[0][field]=id"), SortModel)

    def test_unknown_direction_is_rejected(self):
        with pytest.raises(ValidationError):
            parse_query(
                QueryParams("sort[0][field]=id&sort[0][dir]=sideways"), SortModel
            )

    def test_scalar_sort_is_rejected(self):
        with pytest.raises(ValidationError):
            parse_query(QueryParams("sort=x"), SortModel)


class Item(BaseModel):
    page: PositiveInt = 1


@query_params(Item)
async def item_handler(request, params):
    return PlainTextResponse(str(params.page))


@query_params()
async def bare_handler(request):
    raise ValueError("bad thing")


class TestQueryParamsDecorator:
    def test_injects_validated_params(self):
        assert call(item_handler, "page=3").body == b"3"

    def test_invalid_params_become_400(self):
        response = call(item_handler, "page=0")
        assert response.status_code == 400
        assert b"page" in response.body

    def test_handler_value_errors_become_400(self):
        response = call(bare_handler, "")
        assert response.status_code == 400
        assert b"bad thing" in response.body

    def test_http_exceptions_propagate(self):
        @query_params()
        async def missing(request):
            raise HTTPException(status_code=404, detail="gone")

        with pytest.raises(HTTPException):
            call(missing, "")

    def test_public_signature_stays_request_only(self):
        call(item_handler, "")  # callable as handler(request)


class TestRequireFound:
    def test_known_value_passes_through(self):
        assert require_found("a.log", ["a.log", "b.log"], "Log") == "a.log"

    def test_unknown_value_is_404(self):
        with pytest.raises(HTTPException) as excinfo:
            require_found("../secrets", ["a.log"], "Log")
        assert excinfo.value.status_code == 404
        assert excinfo.value.detail == "Log not found"
