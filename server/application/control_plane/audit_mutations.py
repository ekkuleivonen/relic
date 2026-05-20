from application.uow import UnitOfWork


def clear_audit_events(uow: UnitOfWork) -> int:
    return uow.audit.clear_all()
