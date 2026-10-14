"""Privacy predicates for individual registrations, independent of funding source."""

from uuid import UUID

from sqlalchemy import and_, exists, false, select

from app.models import Asset, AssetType, ProviderConnection, ServiceInstance


def personal_subscription_clause():
    # Both guards keep negation safe for the legacy registry's NULL source/type.
    return and_(
        Asset.source_system.is_not(None),
        Asset.source_system == "membership-registration",
        Asset.asset_type_id.is_not(None),
        Asset.asset_type_id.in_(select(AssetType.id).where(AssetType.code == "saas_subscription")),
    )


def personal_subscription_owner_clause(person_id: UUID | None):
    if person_id is None:
        return false()
    return and_(Asset.created_by_person_id.is_not(None), Asset.created_by_person_id == person_id)


def personal_subscription_privacy_clause(person_id: UUID | None):
    return ~personal_subscription_clause() | personal_subscription_owner_clause(person_id)


def personal_subscription_connection_clause(person_id: UUID | None):
    """Keep ordinary connections unchanged; hide connections to someone else's membership."""
    hidden_membership = exists(
        select(ServiceInstance.id)
        .join(Asset, Asset.id == ServiceInstance.asset_id)
        .where(
            ServiceInstance.id == ProviderConnection.service_instance_id,
            personal_subscription_clause(),
            ~personal_subscription_owner_clause(person_id),
        )
        .correlate(ProviderConnection)
    )
    return ~hidden_membership
