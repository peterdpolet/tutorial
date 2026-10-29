"""
Tests for the Django side of the tracker. Run with the sample project:

    cd sample && python manage.py test tracker

These tests use their own tiny URL configuration (at the bottom of this file)
so the tracker app is proven on its own, independent of the sample app.
"""
import json
from datetime import timedelta
from io import StringIO
from types import SimpleNamespace
from unittest import mock

from django.core.management import call_command
from django.http import JsonResponse
from django.test import TestCase, override_settings
from django.urls import include, path
from django.utils import timezone

from . import trigger
from .models import RuntimeEvent, TraceRun
from .policy import default_authorise
from .tracker import checkpoint, current_trace, traced


# --- the code being traced ---------------------------------------------------
@traced("inner")
def inner(*, n):
    checkpoint("doubling", n=n, password="hunter2", has_token=False)
    if n < 0:
        raise ValueError("bad value from jane.doe@example.com")
    return n * 2


@traced("outer")
def outer(*, n):
    checkpoint("start", n=n)
    return inner(n=n) + 1


def ok_view(request):
    return JsonResponse({"v": outer(n=int(request.GET.get("n", "1")))})


def failing_view(request):
    try:
        outer(n=-1)
    except ValueError as exc:
        return JsonResponse({"detail": str(exc)}, status=409)


def allow_all(request):
    return True


def deny_all(request):
    return False


def explode(request):
    raise RuntimeError("policy blew up")


urlpatterns = [
    path("ok/", ok_view),
    path("fail/", failing_view),
    path("api/tracker/", include("tracker.urls")),
]

MIDDLEWARE = ["tracker.middleware.TrackerMiddleware"]
ON = {"HTTP_X_TRACKER": "1"}


@override_settings(
    ROOT_URLCONF="tracker.tests",
    MIDDLEWARE=MIDDLEWARE,
    TRACKER_ENABLED=True,
    TRACKER_AUTHORISE="tracker.tests.allow_all",
)
class MiddlewareTests(TestCase):
    def test_traced_when_enabled_asked_and_authorised(self):
        resp = self.client.get("/ok/?n=3", **ON)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"v": 7})
        run = TraceRun.objects.get()
        self.assertEqual(resp["X-Tracker-Run"], str(run.pk))
        self.assertEqual((run.method, run.path, run.status_code), ("GET", "/ok/", 200))
        self.assertEqual(run.event_count, 4)  # 2 calls + 2 checkpoints

    def test_tree_shape_and_checkpoints(self):
        self.client.get("/ok/?n=3", **ON)
        run = TraceRun.objects.get()
        events = RuntimeEvent.objects.filter(transaction_id=str(run.pk))
        outer_n, inner_n = events.filter(event_type="call").order_by("seq")
        self.assertEqual((outer_n.qualname, outer_n.parent_seq), ("outer", None))
        self.assertEqual((inner_n.qualname, inner_n.parent_seq), ("inner", outer_n.seq))
        self.assertEqual(inner_n.args_json, {"n": "3"})
        self.assertEqual(inner_n.return_repr, "6")
        labels = {e.label: e.parent_seq for e in events.filter(event_type="checkpoint")}
        self.assertEqual(labels, {"start": outer_n.seq, "doubling": inner_n.seq})

    def test_not_traced_without_header(self):
        resp = self.client.get("/ok/")
        self.assertEqual(TraceRun.objects.count(), 0)
        self.assertNotIn("X-Tracker-Run", resp)

    @override_settings(TRACKER_ENABLED=False)
    def test_not_traced_when_switched_off(self):
        self.client.get("/ok/", **ON)
        self.assertEqual(TraceRun.objects.count(), 0)

    @override_settings(TRACKER_AUTHORISE="tracker.tests.deny_all")
    def test_not_traced_when_not_authorised(self):
        resp = self.client.get("/ok/", **ON)
        self.assertEqual(resp.status_code, 200)  # the request itself still works
        self.assertEqual(TraceRun.objects.count(), 0)

    @override_settings(TRACKER_AUTHORISE="tracker.tests.explode")
    def test_authorise_error_fails_closed(self):
        with self.assertLogs("tracker", level="ERROR"):
            resp = self.client.get("/ok/", **ON)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(TraceRun.objects.count(), 0)

    def test_tracing_stops_with_the_request(self):
        self.client.get("/ok/", **ON)
        self.assertIsNone(current_trace())

    def test_failure_is_recorded_and_redacted(self):
        resp = self.client.get("/fail/", **ON)
        self.assertEqual(resp.status_code, 409)
        # the real response still carries the real message...
        self.assertIn("jane.doe@example.com", resp.json()["detail"])
        # ...but nothing stored contains the address or the password.
        inner_n = RuntimeEvent.objects.get(qualname="inner", event_type="call")
        self.assertIn("ValueError", inner_n.exception_repr)
        everything = json.dumps(
            [
                list(RuntimeEvent.objects.values_list(
                    "args_json", "return_repr", "exception_repr", "label", "values_json")),
                list(TraceRun.objects.values_list("path")),
            ]
        )
        self.assertNotIn("@", everything)
        self.assertNotIn("hunter2", everything)
        # flags stay readable
        doubling = RuntimeEvent.objects.get(label="doubling")
        self.assertEqual(doubling.values_json["has_token"], "False")

    def test_save_failure_never_breaks_the_request(self):
        with mock.patch("tracker.middleware.save_trace", side_effect=RuntimeError("db down")):
            with self.assertLogs("tracker", level="ERROR"):
                resp = self.client.get("/ok/?n=2", **ON)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"v": 5})
        self.assertNotIn("X-Tracker-Run", resp)


@override_settings(
    ROOT_URLCONF="tracker.tests",
    MIDDLEWARE=MIDDLEWARE,
    TRACKER_ENABLED=True,
    TRACKER_AUTHORISE="tracker.tests.allow_all",
)
class ReadApiTests(TestCase):
    def test_list_and_detail(self):
        self.client.get("/ok/?n=3", **ON)
        run = TraceRun.objects.get()

        listing = self.client.get("/api/tracker/runs/").json()["results"]
        self.assertEqual([r["id"] for r in listing], [str(run.pk)])

        tree = self.client.get(f"/api/tracker/runs/{run.pk}/").json()
        self.assertEqual(tree["path"], "/ok/")
        (root,) = tree["calls"]
        self.assertEqual(root["name"], "outer")
        self.assertEqual([c["label"] for c in root["checkpoints"]], ["start"])
        (child,) = root["children"]
        self.assertEqual(child["name"], "inner")
        self.assertEqual(child["returned"], "6")

    def test_reading_traces_does_not_create_runs(self):
        self.client.get("/ok/", **ON)
        resp = self.client.get("/api/tracker/runs/", **ON)  # viewer asks for tracing too
        self.assertNotIn("X-Tracker-Run", resp)
        self.assertEqual(TraceRun.objects.count(), 1)  # still just the one real run

    @override_settings(TRACKER_AUTHORISE="tracker.tests.deny_all")
    def test_forbidden_when_not_authorised(self):
        run = TraceRun.objects.create(
            started_at=timezone.now(), method="GET", path="/x/", status_code=200, duration_ms=1
        )
        self.assertEqual(self.client.get("/api/tracker/runs/").status_code, 403)
        self.assertEqual(self.client.get(f"/api/tracker/runs/{run.pk}/").status_code, 403)

    def test_unknown_run_is_404(self):
        resp = self.client.get("/api/tracker/runs/00000000-0000-0000-0000-000000000000/")
        self.assertEqual(resp.status_code, 404)


class PolicyTests(TestCase):
    def test_default_allows_only_logged_in_staff(self):
        def req(**u):
            return SimpleNamespace(user=SimpleNamespace(**u))

        self.assertTrue(default_authorise(req(is_authenticated=True, is_staff=True)))
        self.assertFalse(default_authorise(req(is_authenticated=True, is_staff=False)))
        self.assertFalse(default_authorise(req(is_authenticated=False, is_staff=True)))
        self.assertFalse(default_authorise(SimpleNamespace()))  # no user at all


class PruneTests(TestCase):
    def test_prune_removes_only_old_runs_and_their_events(self):
        def make(days_old):
            run = TraceRun.objects.create(
                started_at=timezone.now() - timedelta(days=days_old),
                method="GET", path="/x/", status_code=200, duration_ms=1, event_count=1,
            )
            RuntimeEvent.objects.create(
                transaction_id=str(run.pk), seq=1, qualname="n", event_type="call",
            )
            return run

        old, new = make(30), make(1)
        out = StringIO()
        call_command("prune_traces", "--days", "7", stdout=out)
        self.assertFalse(TraceRun.objects.filter(pk=old.pk).exists())
        self.assertTrue(TraceRun.objects.filter(pk=new.pk).exists())
        self.assertEqual(list(RuntimeEvent.objects.values_list("transaction_id", flat=True)), [str(new.pk)])
        self.assertIn("1 runs", out.getvalue())


# --- the one-shot "arm my next request" trigger (trigger.py) --------------------
def fake_user(user_id=1, superuser=True):
    return SimpleNamespace(
        id=user_id, pk=user_id, is_authenticated=True, is_staff=superuser, is_superuser=superuser
    )


class FakeLoginMiddleware:
    """Stands in for AuthenticationMiddleware: logs in user 1 unless the test
    client sends X-Test-Anon."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if "X-Test-Anon" in request.headers:
            request.user = SimpleNamespace(id=None, pk=None, is_authenticated=False, is_staff=False)
        else:
            request.user = fake_user()
        return self.get_response(request)


@override_settings(
    ROOT_URLCONF="tracker.tests",
    MIDDLEWARE=["tracker.tests.FakeLoginMiddleware", "tracker.middleware.TrackerMiddleware"],
    TRACKER_ENABLED=True,
    TRACKER_AUTHORISE="tracker.tests.allow_all",
)
class ArmedTriggerTests(TestCase):
    def setUp(self):
        trigger.redis_conn._store.clear()

    def test_an_armed_request_is_traced_without_the_header_exactly_once(self):
        self.assertTrue(trigger.arm_next_request(fake_user()))
        first = self.client.get("/ok/")
        self.assertIn("X-Tracker-Run", first)
        second = self.client.get("/ok/")
        self.assertNotIn("X-Tracker-Run", second)  # one-shot: the flag was used up
        self.assertEqual(TraceRun.objects.count(), 1)
        self.assertFalse(trigger.is_armed(fake_user()))

    def test_arming_needs_a_superuser(self):
        self.assertFalse(trigger.arm_next_request(fake_user(superuser=False)))
        self.client.get("/ok/")
        self.assertEqual(TraceRun.objects.count(), 0)

    def test_nothing_armed_and_no_header_means_no_trace(self):
        self.client.get("/ok/")
        self.assertEqual(TraceRun.objects.count(), 0)

    @override_settings(TRACKER_AUTHORISE="tracker.tests.deny_all")
    def test_an_unauthorised_request_does_not_use_up_the_arm(self):
        trigger.arm_next_request(fake_user())
        self.client.get("/ok/")
        self.assertEqual(TraceRun.objects.count(), 0)
        self.assertTrue(trigger.is_armed(fake_user()))  # still armed for a later, allowed request

    def test_an_anonymous_request_never_uses_the_arm(self):
        # Contrived on purpose: an arm filed under the same key an anonymous
        # user would produce (id None). Only the middleware's own
        # "must be logged in" guard stands between that and a trace.
        trigger.arm_next_request(fake_user(user_id=None))
        self.client.get("/ok/", HTTP_X_TEST_ANON="1")
        self.assertEqual(TraceRun.objects.count(), 0)

    def test_the_header_works_without_arming_and_leaves_the_arm_alone(self):
        trigger.arm_next_request(fake_user())
        self.client.get("/ok/", **ON)
        self.assertTrue(trigger.is_armed(fake_user()))


# --- static code graph ------------------------------------------------------

from .graph import GraphError, flow, load_graph, match_request  # noqa: E402
from .models import CodeEntity, CodeRelation  # noqa: E402


def _ent(eid, kind="function", name=None, **extra):
    return {"id": eid, "kind": kind, "name": name or eid, "file": "f.py", "line": 1,
            "language": "python", "framework": "django", "parent_id": None,
            "docstring": "", "extra": extra}


def _rel(a, b, t="calls"):
    return {"source_id": a, "target_id": b, "relation_type": t, "extra": {}}


GRAPH = {
    "project": "demo",
    "entities": [
        _ent("ui:click", "ui_action"),
        _ent("api:go", "function"),
        _ent("urls:convert", "url", name="/quotes/<pk>/convert/", methods=["post"]),
        _ent("urls:detail", "url", name="/quotes/<pk>/"),
        _ent("urls:list", "url", name="/quotes/"),
        _ent("views:convert", "view"),
        _ent("models:convert_to_po", "function"),
        _ent("unrelated", "function"),
    ],
    "relations": [
        _rel("ui:click", "api:go"),
        _rel("api:go", "urls:convert", "calls_endpoint"),
        _rel("urls:convert", "views:convert", "routes_to"),
        _rel("urls:detail", "views:convert", "routes_to"),
        _rel("views:convert", "models:convert_to_po"),
        _rel("models:convert_to_po", "views:convert"),  # a cycle must not hang the walk
        _rel("unrelated", "ghost"),  # points nowhere
    ],
}


class GraphLoadTests(TestCase):
    def test_load_stores_entities_and_drops_dangling_relations(self):
        result = load_graph(GRAPH)
        self.assertEqual(result["entities"], 8)
        self.assertEqual(result["relations"], 6)
        self.assertEqual(result["dropped_relations"], 1)
        self.assertEqual(CodeEntity.objects.filter(project="demo").count(), 8)

    def test_reload_replaces_rather_than_adds(self):
        load_graph(GRAPH)
        smaller = {"project": "demo", "entities": [_ent("only")], "relations": []}
        load_graph(smaller)
        self.assertEqual(list(CodeEntity.objects.values_list("entity_id", flat=True)), ["only"])
        self.assertEqual(CodeRelation.objects.count(), 0)

    def test_reload_leaves_other_projects_alone(self):
        load_graph(GRAPH)
        load_graph({"project": "other", "entities": [_ent("x")], "relations": []})
        load_graph({"project": "other", "entities": [_ent("y")], "relations": []})
        self.assertEqual(CodeEntity.objects.filter(project="demo").count(), 8)

    def test_bad_input_is_refused_and_changes_nothing(self):
        load_graph(GRAPH)
        for bad in ({"entities": []}, "nope", {"entities": [], "relations": []}):  # last: no project
            with self.assertRaises(GraphError):
                load_graph(bad)
        self.assertEqual(CodeEntity.objects.filter(project="demo").count(), 8)

    def test_failed_load_rolls_back(self):
        load_graph(GRAPH)
        broken = {"project": "demo", "entities": [_ent("a")], "relations": [{"source_id": "a"}]}
        with self.assertRaises(KeyError):
            load_graph(broken)
        self.assertEqual(CodeEntity.objects.filter(project="demo").count(), 8)

    def test_explicit_project_overrides_file(self):
        load_graph(GRAPH, project="renamed")
        self.assertEqual(CodeEntity.objects.filter(project="renamed").count(), 8)

    def test_command_loads_a_file(self):
        import os, tempfile
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "g.json")
            with open(p, "w") as fh:
                json.dump(GRAPH, fh)
            out = StringIO()
            call_command("load_graph", p, stdout=out)
        self.assertIn("Loaded 8 entities and 6 relations", out.getvalue())


class GraphQueryTests(TestCase):
    def setUp(self):
        load_graph(GRAPH)

    def test_flow_follows_outgoing_edges_and_terminates_on_cycles(self):
        result = flow("demo", "ui:click")
        ids = {e["id"] for e in result["entities"]}
        self.assertEqual(ids, {"ui:click", "api:go", "urls:convert", "views:convert", "models:convert_to_po"})
        self.assertNotIn("urls:detail", ids)  # it points AT the view; nothing leads from the click to it

    def test_flow_unknown_start(self):
        self.assertIsNone(flow("demo", "nope"))

    def test_match_picks_route_through_mount_prefix(self):
        found = match_request("demo", "POST", "/api/quotes/7/convert/")
        self.assertEqual(found["url"]["id"], "urls:convert")
        self.assertEqual(found["handlers"], ["views:convert"])

    def test_match_respects_methods(self):
        self.assertIsNone(match_request("demo", "GET", "/api/quotes/7/convert/"))

    def test_match_does_not_confuse_list_and_detail(self):
        self.assertEqual(match_request("demo", "GET", "/api/quotes/")["url"]["id"], "urls:list")
        self.assertEqual(match_request("demo", "GET", "/api/quotes/7/")["url"]["id"], "urls:detail")

    def test_match_ignores_query_string_and_partial_names(self):
        self.assertEqual(match_request("demo", "GET", "/api/quotes/?page=2")["url"]["id"], "urls:list")
        self.assertIsNone(match_request("demo", "GET", "/api/subquotes/"))
        self.assertIsNone(match_request("demo", "GET", "/api/other/"))


@override_settings(
    ROOT_URLCONF="tracker.tests",
    MIDDLEWARE=MIDDLEWARE,
    TRACKER_ENABLED=True,
    TRACKER_AUTHORISE="tracker.tests.allow_all",
)
class GraphApiTests(TestCase):
    def setUp(self):
        load_graph(GRAPH)

    def test_projects_and_graph(self):
        self.assertEqual(self.client.get("/api/tracker/graph/").json(), {"projects": ["demo"]})
        data = self.client.get("/api/tracker/graph/demo/").json()
        self.assertEqual(len(data["entities"]), 8)
        self.assertEqual(len(data["relations"]), 6)

    def test_flow_and_match_endpoints(self):
        data = self.client.get("/api/tracker/graph/demo/flow/", {"start": "api:go"}).json()
        self.assertIn("views:convert", {e["id"] for e in data["entities"]})
        m = self.client.get("/api/tracker/graph/demo/match/", {"method": "POST", "path": "/api/quotes/1/convert/"})
        self.assertEqual(m.json()["handlers"], ["views:convert"])

    def test_404s(self):
        self.assertEqual(self.client.get("/api/tracker/graph/nope/").status_code, 404)
        self.assertEqual(self.client.get("/api/tracker/graph/demo/flow/?start=zzz").status_code, 404)
        self.assertEqual(self.client.get("/api/tracker/graph/demo/match/?path=/zzz/").status_code, 404)

    @override_settings(TRACKER_AUTHORISE="tracker.tests.deny_all")
    def test_all_graph_endpoints_forbidden_when_not_authorised(self):
        for url in ("/api/tracker/graph/", "/api/tracker/graph/demo/",
                    "/api/tracker/graph/demo/flow/?start=api:go", "/api/tracker/graph/demo/match/?path=/quotes/"):
            self.assertEqual(self.client.get(url).status_code, 403, url)



# --- dev-only tracing of anonymous requests (register / login flows) ---------
FAKE_PASSWORD = "Tut0rial-Pass!"
FAKE_EMAIL = "learner@example.com"
FAKE_TOKEN = "tok_Tut0rialSecretValue"


@traced("create_account")
def create_account(*, email, password, profile):
    checkpoint("validated", email=email, password=password, note="strong enough")
    checkpoint("issuing", reset_link=f"https://example.com/reset?t={FAKE_TOKEN}", profile=profile)
    return {"id": 1, "email": email}


def register_view(request):
    create_account(email=FAKE_EMAIL, password=FAKE_PASSWORD, profile={"password": FAKE_PASSWORD, "plan": "free"})
    return JsonResponse({"ok": True})


urlpatterns.append(path("api/auth/register/", register_view))
urlpatterns.append(path("other/", ok_view))

ANON = {"REMOTE_ADDR": "127.0.0.1"}


def anon_request(path_, **meta):
    from django.test import RequestFactory

    req = RequestFactory().get(path_, **{"REMOTE_ADDR": "127.0.0.1", **meta})
    req.user = SimpleNamespace(is_authenticated=False, is_staff=False)
    return req


@override_settings(DEBUG=True, TRACKER_DEV_ANON_PREFIXES=["/api/auth/"])
class DevAuthorisePolicyTests(TestCase):
    def test_allows_anonymous_on_listed_prefix_in_debug_from_loopback(self):
        from .policy import dev_authorise

        self.assertTrue(dev_authorise(anon_request("/api/auth/register/")))

    def test_refuses_unlisted_path(self):
        from .policy import dev_authorise

        self.assertFalse(dev_authorise(anon_request("/other/")))

    @override_settings(DEBUG=False)
    def test_refuses_when_debug_is_off(self):
        from .policy import dev_authorise

        self.assertFalse(dev_authorise(anon_request("/api/auth/register/")))

    @override_settings(TRACKER_DEV_ANON_PREFIXES=[])
    def test_nothing_is_open_until_prefixes_are_listed(self):
        from .policy import dev_authorise

        self.assertFalse(dev_authorise(anon_request("/api/auth/register/")))

    def test_refuses_non_loopback_caller(self):
        from .policy import dev_authorise

        self.assertFalse(dev_authorise(anon_request("/api/auth/register/", REMOTE_ADDR="203.0.113.9")))

    @override_settings(TRACKER_DEV_LOOPBACK_ONLY=False)
    def test_loopback_rule_can_be_switched_off_for_docker_dev(self):
        from .policy import dev_authorise

        self.assertTrue(dev_authorise(anon_request("/api/auth/register/", REMOTE_ADDR="172.18.0.1")))

    @override_settings(TRACKER_DEV_ANON_PREFIXES=["/api/"])
    def test_never_opens_the_trace_viewer_itself(self):
        from .policy import dev_authorise

        self.assertFalse(dev_authorise(anon_request("/api/tracker/runs/")))

    def test_logged_in_staff_still_allowed_anywhere(self):
        from .policy import dev_authorise

        req = anon_request("/other/")
        req.user = SimpleNamespace(is_authenticated=True, is_staff=True)
        self.assertTrue(dev_authorise(req))


@override_settings(
    ROOT_URLCONF="tracker.tests",
    MIDDLEWARE=MIDDLEWARE,
    TRACKER_ENABLED=True,
    TRACKER_AUTHORISE="tracker.policy.dev_authorise",
    TRACKER_DEV_ANON_PREFIXES=["/api/auth/"],
    DEBUG=True,
)
class AnonymousRegisterTraceTests(TestCase):
    """End to end: an anonymous register request is traced, and the redaction
    audit proves none of the fake secrets reach the database."""

    def test_anonymous_register_is_traced(self):
        resp = self.client.get("/api/auth/register/", **ON, **ANON)
        self.assertEqual(resp.status_code, 200)
        run = TraceRun.objects.get()
        self.assertIsNone(run.user_id)
        self.assertEqual(run.path, "/api/auth/register/")

    def test_header_is_still_required(self):
        self.client.get("/api/auth/register/", **ANON)
        self.assertEqual(TraceRun.objects.count(), 0)

    def test_unlisted_path_is_not_traced_for_anonymous(self):
        self.client.get("/other/", **ON, **ANON)
        self.assertEqual(TraceRun.objects.count(), 0)

    @override_settings(DEBUG=False)
    def test_not_traced_when_debug_off(self):
        self.client.get("/api/auth/register/", **ON, **ANON)
        self.assertEqual(TraceRun.objects.count(), 0)

    def test_anonymous_cannot_read_traces(self):
        self.client.get("/api/auth/register/", **ON, **ANON)
        resp = self.client.get("/api/tracker/runs/", **ANON)
        self.assertEqual(resp.status_code, 403)

    def test_redaction_audit_no_fake_secret_is_stored(self):
        self.client.get("/api/auth/register/", **ON, **ANON)
        self.assertGreater(RuntimeEvent.objects.count(), 0)
        dump = json.dumps(
            list(
                RuntimeEvent.objects.values(
                    "event_type", "qualname", "label", "args_json", "return_repr", "exception_repr", "values_json"
                )
            ),
            default=str,
        )
        for secret in (FAKE_PASSWORD, FAKE_EMAIL, FAKE_TOKEN, "Tut0rial"):
            self.assertNotIn(secret, dump, f"{secret!r} leaked into stored trace events")
