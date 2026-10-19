# n8n prototype

The first version of this project: four n8n workflows exposed as webhooks, called one after another
by the frontend. They are kept here for reference. The Python service in `backend/` replaces them.

| File | Webhook | Role |
|---|---|---|
| `1-routing-agent.json` | `/routingAgent` | Validates and routes the question |
| `2-sql-agent.json` | `/sqlAgent` | Generates SQL and calls the SQL execution API |
| `3-analysis-agent.json` | `/analysisAgent` | Explains the result |
| `4-plot-agent.json` | `/plotAgent` | Produces a chart configuration |

Credentials, API keys and captured test data have been removed. To import a workflow, create
your own Gemini/Postgres credentials in n8n and set `DB_API_KEY` in the n8n environment.
