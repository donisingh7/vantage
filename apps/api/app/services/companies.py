from uuid import UUID

from app.models import Company, watchlist_companies
from app.schemas.companies import CompanyCreate, CompanyUpdate
from app.services.base import WorkspaceResourceService


class CompanyService(WorkspaceResourceService[Company]):
    model = Company
    label = "Company"
    search_fields = ("name", "domain")
    link_table = watchlist_companies
    link_column = "company_id"

    async def create(self, payload: CompanyCreate) -> Company:
        await self.ensure_unique(
            "domain", payload.domain, message="A company with this domain already exists in this workspace"
        )
        company = Company(workspace_id=self.workspace_id, **payload.model_dump())
        await self.repository.add(company)
        await self.session.commit()
        return company

    async def update(self, company_id: UUID, payload: CompanyUpdate) -> Company:
        company = await self.get(company_id)
        changes = payload.model_dump(exclude_unset=True)
        if "domain" in changes:
            await self.ensure_unique(
                "domain",
                changes["domain"],
                message="A company with this domain already exists in this workspace",
                exclude_id=company_id,
            )
        self.apply_changes(company, changes)
        await self.session.commit()
        return company
