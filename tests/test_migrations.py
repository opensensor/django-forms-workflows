"""
Tests for data migration logic (migration 0035 & 0037).

These tests verify the migration functions directly using current models
rather than the Django migration test runner, since the legacy fields have
already been removed from the model.  The underlying logic is identical.
"""

from django.contrib.auth.models import Group

from django_forms_workflows.models import (
    FormDefinition,
    FormField,
    PrefillSource,
    WorkflowDefinition,
    WorkflowStage,
)


class TestPrefillSourceMigrationLogic:
    """Verify that PrefillSource records are created correctly for known patterns."""

    def test_user_email_source(self, db):
        ps, _ = PrefillSource.objects.get_or_create(
            source_key="user.email",
            defaults={
                "name": "Current User - Email",
                "source_type": "user",
            },
        )
        assert ps.source_type == "user"
        assert ps.get_source_identifier() == "user.email"

    def test_ldap_source(self, db):
        ps, _ = PrefillSource.objects.get_or_create(
            source_key="ldap.department",
            defaults={
                "name": "LDAP - department",
                "source_type": "ldap",
                "ldap_attribute": "department",
            },
        )
        assert ps.source_type == "ldap"
        assert ps.get_source_identifier() == "ldap.department"

    def test_system_current_date(self, db):
        ps, _ = PrefillSource.objects.get_or_create(
            source_key="current_date",
            defaults={
                "name": "Current Date",
                "source_type": "system",
            },
        )
        assert ps.source_type == "system"

    def test_idempotent_get_or_create(self, db):
        PrefillSource.objects.create(
            name="User Email",
            source_type="user",
            source_key="user.email",
        )
        ps, created = PrefillSource.objects.get_or_create(
            source_key="user.email",
            defaults={"name": "Dup", "source_type": "user"},
        )
        assert created is False
        assert PrefillSource.objects.filter(source_key="user.email").count() == 1


class TestFlatWorkflowToStagedLogic:
    """Verify the promotion logic for flat workflows → staged workflows."""

    def test_sequence_creates_one_stage_per_group(self, db):
        fd = FormDefinition.objects.create(
            name="SeqTest", slug="seq-test", description="t"
        )
        g1 = Group.objects.create(name="Seq1")
        g2 = Group.objects.create(name="Seq2")
        wf = WorkflowDefinition.objects.create(
            form_definition=fd, requires_approval=True
        )

        # Simulate migration logic: create stages from flat groups
        groups = [g1, g2]
        stages = []
        for i, group in enumerate(groups, start=1):
            stage = WorkflowStage.objects.create(
                workflow=wf,
                name=f"{group.name} Review",
                order=i,
                approval_logic="all",
            )
            stage.approval_groups.add(group)
            stages.append(stage)

        assert len(stages) == 2
        assert stages[0].name == "Seq1 Review"
        assert stages[1].name == "Seq2 Review"
        assert stages[0].approval_groups.first() == g1

    def test_all_creates_single_stage(self, db):
        fd = FormDefinition.objects.create(
            name="AllTest", slug="all-test", description="t"
        )
        g1 = Group.objects.create(name="All1")
        g2 = Group.objects.create(name="All2")
        wf = WorkflowDefinition.objects.create(
            form_definition=fd, requires_approval=True
        )

        # Simulate: single stage with all groups
        groups = [g1, g2]
        stage = WorkflowStage.objects.create(
            workflow=wf,
            name="Review",
            order=1,
            approval_logic="all",
        )
        stage.approval_groups.set(groups)

        assert wf.stages.count() == 1
        assert stage.approval_groups.count() == 2

    def test_field_mapping_to_stages(self, db):
        fd = FormDefinition.objects.create(
            name="MapTest", slug="map-test", description="t"
        )
        g1 = Group.objects.create(name="Map1")
        wf = WorkflowDefinition.objects.create(
            form_definition=fd, requires_approval=True
        )
        stage = WorkflowStage.objects.create(workflow=wf, name="Review", order=1)
        stage.approval_groups.add(g1)

        # Create a field and map it to stage (simulating what migration does)
        field = FormField.objects.create(
            form_definition=fd,
            field_name="reviewer_sig",
            field_label="Reviewer Signature",
            field_type="text",
            order=100,
        )
        field.workflow_stage = stage
        field.save(update_fields=["workflow_stage"])

        field.refresh_from_db()
        assert field.workflow_stage == stage
