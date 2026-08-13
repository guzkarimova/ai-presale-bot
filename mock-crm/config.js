const CONFIG={mode:'local',n8nBaseUrl:'https://n8n.vsellm.info',crmWebhookPath:'/webhook/ai-sales-monitor/crm-event',demoMode:true};
async function sendCrmEvent(event_type,deal_id,payload={}){const r=await fetch(CONFIG.n8nBaseUrl+CONFIG.crmWebhookPath,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({event_type,deal_id,payload})});return r.json()}
