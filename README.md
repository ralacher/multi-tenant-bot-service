# Multi Tenant Bot Service

Python Microsoft 365 Agents SDK bot hosted on Azure App Service and connected through Azure Bot Service to Microsoft Teams. The bot forwards messages to a Foundry prompt agent by using `azure-ai-projects` (2.x).

## Multi-tenant topology (Tenant A / Tenant B)

This solution is designed for cross-tenant Teams usage:

1. Users interact with the Teams app in Tenant A.
2. Bot Service and App Service are hosted in Tenant B.
3. Bot app registration is configured as multi-tenant.
4. Azure Bot Service forwards activities to App Service `/api/messages`.
5. App Service calls Foundry and returns responses back to Teams.

## Prerequisites

1. Python 3.11+
2. Azure CLI and Azure Developer CLI (`azd`)
3. Entra app registration for bot auth (client ID and secret)
4. Foundry project access for the runtime identity (at least Foundry User)

## Runtime configuration

Required settings:

- `MICROSOFT_APP_ID`
- `MICROSOFT_APP_PASSWORD`
- `MICROSOFT_APP_TENANT_ID` (Tenant B app registration tenant)
- `FOUNDRY_PROJECT_ENDPOINT`
- `FOUNDRY_AGENT_NAME` (preferred)

Optional settings:

- `FOUNDRY_AGENT_ID` (fallback if name is not used)
- `PORT`
- `APPLICATIONINSIGHTS_CONNECTION_STRING`

Use [.env.example](.env.example) as the local template.

## Local run

1. Create and activate a virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Create `.env` from `.env.example` and fill values.
4. Start the app:

```bash
python src/app.py
```

5. Test with Agents Playground (`teamsapptester`) against `http://127.0.0.1:3978/api/messages`.

## IaC deployment options

### Option A: Provision new resources with IaC

```bash
azd env new dev
azd env set AZURE_LOCATION eastus2
azd env set BICEP_PARAM_namePrefix bot
azd env set BICEP_PARAM_botAppId <bot-app-client-id>
azd env set BICEP_PARAM_botAppSecret <bot-app-client-secret>
azd env set BICEP_PARAM_botAppTenantId <tenant-b-id>
azd env set BICEP_PARAM_foundryProjectName proj-default
azd env set BICEP_PARAM_foundryModelDeploymentName gpt-5.4
azd env set BICEP_PARAM_foundryModelName gpt-5.4
azd env set BICEP_PARAM_foundryModelCapacity 10
azd env set BICEP_PARAM_foundryAgentName prompt-agent
azd up
```

### Option B: Reuse existing resources with IaC

Provide existing resources by parameters:

- `BICEP_PARAM_existingAppServicePlanResourceId`
- `BICEP_PARAM_existingFoundryProjectEndpoint`

Then disable model creation if Foundry resources already exist:

```bash
azd env set BICEP_PARAM_deployFoundryModel false
```

Example minimal flow:

```bash
azd env new prod
azd env set AZURE_LOCATION eastus2
azd env set BICEP_PARAM_namePrefix bot
azd env set BICEP_PARAM_botAppId <bot-app-client-id>
azd env set BICEP_PARAM_botAppSecret <bot-app-client-secret>
azd env set BICEP_PARAM_botAppTenantId <tenant-b-id>
azd env set BICEP_PARAM_existingAppServicePlanResourceId </subscriptions/.../serverfarms/...>
azd env set BICEP_PARAM_existingFoundryProjectEndpoint <https://.../api/projects/...>
azd env set BICEP_PARAM_foundryAgentName <existing-agent-name>
azd env set BICEP_PARAM_deployFoundryModel false
azd up
```

## Bootstrap a Foundry prompt agent (optional)

If you provisioned a new Foundry project and still need an agent:

```bash
set FOUNDRY_PROJECT_ENDPOINT=https://<foundry-resource>.services.ai.azure.com/api/projects/proj-default
set FOUNDRY_MODEL_DEPLOYMENT_NAME=gpt-5.4
set FOUNDRY_AGENT_NAME=prompt-agent
python scripts/bootstrap_foundry_agent.py
```

## Teams app package

Use [teams/appPackage/manifest.json](teams/appPackage/manifest.json) as a template. Replace placeholders before packaging:

- `${BOT_APP_ID}`
- `${BOT_DOMAIN}`

Then zip only these files from [teams/appPackage](teams/appPackage):

- `manifest.json`
- `default-color-icon.png`
- `default-outline-icon.png`

Upload the package to Tenant A.

## Security notes

- Do not commit secrets to source control.
- Use Key Vault references for production secrets in App Service.
- Restrict tenant/app permissions by least privilege.
