"""
Where traces are stored: two tables.

    RuntimeEvent   one row per traced call and one row per checkpoint
                   (unchanged from the 24 Sep design: a trace is rebuilt as a
                   tree from parent_seq, and "every capture that called X"
                   is a plain WHERE qualname = ...)
    TraceRun       one header row per traced REQUEST: which URL, what status,
                   how long, who asked. A viewer needs this to list runs;
                   the events table holds nothing about the request itself.

The link between them is the transaction id: RuntimeEvent.transaction_id is
the same value as str(TraceRun.id). There is deliberately no foreign key
(the same call made on 24 Sep for created_by_id): the events table stays
self-contained, and pruning deletes both sides explicitly.

"seq" is the order things happened in (calls and checkpoints share one
counter), so sorting by seq replays the story. parent_seq is the seq of the
call a row sits under; for a checkpoint that is the call it ran inside.

Only text that has already been through the redaction policy is stored here
(see redaction.py). These tables hold no raw request data.
"""
import uuid

from django.db import models


class RuntimeEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    transaction_id = models.CharField(max_length=200)
    seq = models.IntegerField()
    parent_seq = models.IntegerField(null=True, blank=True)
    qualname = models.CharField(max_length=300)
    event_type = models.CharField(max_length=20)  # 'call' or 'checkpoint'
    label = models.CharField(max_length=200, null=True, blank=True)
    args_json = models.JSONField(null=True, blank=True)
    return_repr = models.TextField(null=True, blank=True)
    exception_repr = models.TextField(null=True, blank=True)
    values_json = models.JSONField(null=True, blank=True)
    elapsed_ms = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    created_by_id = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'runtime_events'
        indexes = [
            models.Index(fields=['transaction_id', 'seq'], name='idx_runtime_events_transaction'),
        ]


class TraceRun(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    started_at = models.DateTimeField(db_index=True)
    method = models.CharField(max_length=10)
    path = models.CharField(max_length=500)
    status_code = models.PositiveSmallIntegerField()
    duration_ms = models.FloatField()
    # Who asked for the trace: the user's id only, never a name or email.
    user_id = models.BigIntegerField(null=True, blank=True)
    # Rows written to runtime_events for this run (calls + checkpoints).
    event_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"{self.method} {self.path} [{self.status_code}]"


class CodeEntity(models.Model):
    """One thing found in the code by the discoverer: a class, method, url, component..."""

    project = models.CharField(max_length=100)
    entity_id = models.CharField(max_length=500)  # e.g. "procurement/models.py:Quote.convert_to_po"
    kind = models.CharField(max_length=30)
    name = models.CharField(max_length=300)
    file = models.CharField(max_length=500, blank=True)
    line = models.PositiveIntegerField(null=True, blank=True)
    language = models.CharField(max_length=20, blank=True)
    framework = models.CharField(max_length=30, blank=True)
    parent_id = models.CharField(max_length=500, null=True, blank=True)
    docstring = models.TextField(blank=True)
    extra = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "code_entities"
        constraints = [
            models.UniqueConstraint(fields=["project", "entity_id"], name="uniq_code_entity")
        ]
        indexes = [models.Index(fields=["project", "kind"], name="idx_code_entity_kind")]


class CodeRelation(models.Model):
    """A directed link between two entities: calls, routes_to, calls_endpoint ..."""

    project = models.CharField(max_length=100)
    source_id = models.CharField(max_length=500)
    target_id = models.CharField(max_length=500)
    relation_type = models.CharField(max_length=30)
    extra = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "code_relations"
        indexes = [models.Index(fields=["project", "source_id"], name="idx_code_rel_source")]
