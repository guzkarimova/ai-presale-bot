import asyncio
import json
import logging
from pathlib import Path

from aiogram import Bot

from services.application_service import (
    get_application,
    get_pending_presale_application_ids,
    mark_manager_notified,
    mark_processing_error,
    save_presale_analysis,
    save_proposal,
    save_pricing_result,
)
from services.google_docs_service import GoogleDocsService
from services.manager_notifier import ManagerNotifier
from services.presale_analyzer import PresaleAnalyzer
from services.pricing_service import PricingService
from services.proposal_generator import ProposalGenerator
from schemas.pricing import PricingResult


_background_tasks: set[asyncio.Task] = set()


def schedule_presale_processing(bot: Bot, application_id: int) -> None:
    task = asyncio.create_task(process_presale(bot, application_id), name=f"presale-{application_id}")
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


async def recover_pending_presale_tasks(bot: Bot) -> None:
    application_ids = await asyncio.to_thread(get_pending_presale_application_ids)
    for application_id in application_ids:
        logging.info("Recovering pending presale processing for application %s", application_id)
        schedule_presale_processing(bot, application_id)


async def process_presale(bot: Bot, application_id: int) -> None:
    application = await asyncio.to_thread(get_application, application_id)
    if application is None:
        return
    analysis = None
    pricing: PricingResult | None = None
    pricing_recalculated = False
    if application.presale_analysis_json:
        try:
            from schemas.presale import PresaleAnalysis

            analysis = PresaleAnalysis.model_validate_json(application.presale_analysis_json)
        except Exception:
            logging.warning("Stored AI analysis is invalid for application %s; regenerating", application_id)
    if application.pricing_result_json:
        try:
            pricing = PricingResult.model_validate_json(application.pricing_result_json)
        except Exception:
            logging.warning("Stored pricing result is invalid for application %s; recalculating", application_id)
    pdf_path: Path | None = Path(application.proposal_path) if application.proposal_path else None
    if pdf_path is not None and not pdf_path.exists():
        pdf_path = None
    error: str | None = None
    try:
        if analysis is None:
            analysis = await PresaleAnalyzer().analyze(application)
            analysis_json = analysis.model_dump_json(by_alias=True)
            await asyncio.to_thread(
                save_presale_analysis,
                application_id,
                analysis_json,
                {
                    "selected_solution": analysis.recommended_solution_name,
                    "selected_services_json": json.dumps(analysis.selected_services, ensure_ascii=False),
                    "analyzed_integrations_json": json.dumps([item.model_dump() for item in analysis.integrations], ensure_ascii=False),
                    "complexity": analysis.complexity,
                    "clarifications_json": json.dumps(analysis.clarifications_needed, ensure_ascii=False),
                },
            )
            application = await asyncio.to_thread(get_application, application_id)
        if pricing is None:
            unchecked_integrations = [item.name for item in analysis.integrations if item.status == "needs_check"]
            pricing = PricingService().calculate(analysis.selected_services, unchecked_integrations)
            pricing_recalculated = True
            await asyncio.to_thread(
                save_pricing_result,
                application_id,
                pricing.model_dump_json(),
                {
                    "calculated_price": pricing.calculated_price,
                    "final_price": pricing.final_price,
                    "project_level": pricing.project_level,
                    "pricing_timeline": pricing.timeline_text,
                    "pricing_manual_check": pricing.manual_check_required,
                    "pricing_manual_reasons_json": json.dumps(pricing.manual_check_reasons, ensure_ascii=False),
                    "proposal_status": "PRICED",
                },
            )
            logging.info(
                "Pricing calculated for application %s: calculated=%s final=%s level=%s manual=%s",
                application_id,
                pricing.calculated_price,
                pricing.final_price,
                pricing.project_level,
                pricing.manual_check_required,
            )
            application = await asyncio.to_thread(get_application, application_id)
        if pricing_recalculated:
            pdf_path = None
        if pdf_path is None:
            try:
                pdf_path = await asyncio.to_thread(ProposalGenerator().generate, application, analysis, pricing)
                await asyncio.to_thread(save_proposal, application_id, str(pdf_path))
            except Exception as exc:
                logging.exception("PDF generation failed for application %s", application_id)
                error = f"PDF generation failed: {exc}"
    except Exception as exc:
        logging.exception("Presale analysis or pricing failed for application %s", application_id)
        error = f"Presale analysis or pricing failed: {exc}"

    application = await asyncio.to_thread(get_application, application_id)
    if error:
        await asyncio.to_thread(mark_processing_error, application_id, error)
        application = await asyncio.to_thread(get_application, application_id)
    if analysis:
        services = ", ".join(analysis.selected_services)
        integrations = ", ".join(item.name for item in analysis.integrations)
        google_result = {
            "status": application.status,
            "analysis": analysis.model_dump_json(by_alias=True),
            "solution": analysis.recommended_solution_name,
            "services": services,
            "integrations": integrations,
            "complexity": pricing.project_level if pricing else analysis.complexity,
            "timeline": pricing.timeline_text if pricing else "Требуется ручная оценка",
            "price": pricing.price_text if pricing else "Требуется ручная оценка",
            "calculated_price": pricing.calculated_price if pricing else "",
            "final_price": pricing.final_price if pricing and pricing.final_price is not None else "",
            "project_level": pricing.project_level if pricing else "CUSTOM",
            "manual_check_required": pricing.manual_check_required if pricing else True,
            "manual_check_reasons": "\n".join(pricing.manual_check_reasons) if pricing else "AI-анализ не сформирован",
            "proposal_status": application.proposal_status or application.status,
            "clarifications": "\n".join(analysis.clarifications_needed),
            "pdf": pdf_path.name if pdf_path else "",
            "proposal_needs_update": application.proposal_needs_update,
        }
        await asyncio.to_thread(GoogleDocsService.sync_presale_result, application, google_result)
    else:
        await asyncio.to_thread(
            GoogleDocsService.sync_presale_result,
            application,
            {
                "status": application.status,
                "analysis": "AI-анализ не сформирован — требуется ручная обработка",
                "solution": "",
                "services": "",
                "integrations": "",
                "complexity": "",
                "timeline": "",
                "price": "",
                "calculated_price": "",
                "final_price": "",
                "project_level": "CUSTOM",
                "manual_check_required": True,
                "manual_check_reasons": "AI-анализ не сформирован",
                "proposal_status": application.proposal_status or "MANUAL_REVIEW",
                "clarifications": "Требуется ручная обработка",
                "pdf": "",
                "proposal_needs_update": application.proposal_needs_update,
            },
        )
    try:
        await ManagerNotifier().send_new_lead(bot, application, analysis, pricing, pdf_path, error)
        if ManagerNotifier.configured():
            await asyncio.to_thread(mark_manager_notified, application_id)
    except Exception:
        logging.exception("Failed to notify manager for application %s", application_id)
        await asyncio.to_thread(mark_processing_error, application_id, "Manager notification failed")
