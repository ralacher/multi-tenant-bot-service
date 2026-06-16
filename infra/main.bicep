targetScope = 'resourceGroup'

@description('Deployment location for all resources.')
param location string = resourceGroup().location

@description('Base name for the resources.')
param namePrefix string = 'bot'

@description('Existing Entra app (client) ID used by Azure Bot Service.')
param botAppId string

@secure()
@description('Existing Entra app client secret for the bot app registration.')
param botAppSecret string

@description('Entra tenant ID that owns the bot app registration (Tenant B in cross-tenant scenarios).')
param botAppTenantId string = tenant().tenantId

@description('Optional Foundry agent ID. Leave empty until bootstrap script creates the prompt agent.')
param foundryAgentId string = ''

@description('Optional Foundry agent name. Preferred over foundryAgentId with the newer SDK.')
param foundryAgentName string = ''

@description('Name for the Foundry project resource.')
param foundryProjectName string = 'proj-default'

@description('Model deployment name used by your app and bootstrap script.')
param foundryModelDeploymentName string = 'gpt-5.4'

@description('Underlying model name to deploy in Foundry.')
param foundryModelName string = 'gpt-5.4'

@description('Model version for the deployed Foundry model.')
param foundryModelVersion string = '2026-03-05'

@description('Capacity assigned to the model deployment (TPM units vary by model).')
param foundryModelCapacity int = 10

@description('SKU name for the model deployment.')
param foundryModelSkuName string = 'GlobalStandard'

@description('Set to false to provision infra without creating the model deployment (useful when quota is unavailable).')
param deployFoundryModel bool = true

@description('Optional existing Foundry project endpoint. If provided, Foundry account/project/model resources are not created by this template.')
param existingFoundryProjectEndpoint string = ''

@description('Linux runtime for App Service.')
param linuxFxVersion string = 'PYTHON|3.11'

@description('Set to false to skip Azure Bot Service resource creation during initial infra provisioning.')
param deployBot bool = true

@description('Optional existing App Service Plan resource ID. If provided, infra reuses it and skips plan creation.')
param existingAppServicePlanResourceId string = ''

@description('SKU name for a newly created App Service Plan when existingAppServicePlanResourceId is not provided.')
param appServicePlanSkuName string = 'P0v3'

@description('SKU tier for a newly created App Service Plan when existingAppServicePlanResourceId is not provided.')
param appServicePlanSkuTier string = 'PremiumV3'

@description('SKU capacity for a newly created App Service Plan when existingAppServicePlanResourceId is not provided.')
param appServicePlanSkuCapacity int = 1

var appServiceName = toLower('${namePrefix}-app-${uniqueString(resourceGroup().id)}')
var appServicePlanName = toLower('${namePrefix}-asp-${uniqueString(resourceGroup().id)}')
var appInsightsName = '${namePrefix}-appi'
var botServiceName = '${namePrefix}-bot'
var foundryAccountName = toLower('fa${uniqueString(resourceGroup().id, namePrefix)}')
var defaultFoundryProjectEndpoint = 'https://${foundryAccountName}.services.ai.azure.com/api/projects/${foundryProjectName}'
var foundryProjectEndpoint = empty(existingFoundryProjectEndpoint)
  ? defaultFoundryProjectEndpoint
  : existingFoundryProjectEndpoint

resource appServicePlan 'Microsoft.Web/serverfarms@2023-12-01' = if (empty(existingAppServicePlanResourceId)) {
  name: appServicePlanName
  location: location
  kind: 'linux'
  sku: {
    name: appServicePlanSkuName
    tier: appServicePlanSkuTier
    capacity: appServicePlanSkuCapacity
  }
  properties: {
    reserved: true
  }
}

var appServicePlanId = empty(existingAppServicePlanResourceId)
  ? appServicePlan.id
  : existingAppServicePlanResourceId

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: appInsightsName
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: null
  }
}

resource foundryAccount 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' = if (empty(existingFoundryProjectEndpoint)) {
  name: foundryAccountName
  location: location
  kind: 'AIServices'
  identity: {
    type: 'SystemAssigned'
  }
  sku: {
    name: 'S0'
  }
  properties: {
    allowProjectManagement: true
    customSubDomainName: foundryAccountName
    publicNetworkAccess: 'Enabled'
  }
}

resource foundryProject 'Microsoft.CognitiveServices/accounts/projects@2025-04-01-preview' = if (empty(existingFoundryProjectEndpoint)) {
  name: foundryProjectName
  parent: foundryAccount
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {}
}

resource foundryModelDeployment 'Microsoft.CognitiveServices/accounts/deployments@2026-03-15-preview' = if (empty(existingFoundryProjectEndpoint) && deployFoundryModel) {
  name: foundryModelDeploymentName
  parent: foundryAccount
  sku: {
    name: foundryModelSkuName
    capacity: foundryModelCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: foundryModelName
      version: foundryModelVersion
    }
    versionUpgradeOption: 'OnceNewDefaultVersionAvailable'
  }
}

resource webApp 'Microsoft.Web/sites@2023-12-01' = {
  name: appServiceName
  location: location
  kind: 'app,linux'
  tags: {
    'azd-service-name': 'botapp'
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    serverFarmId: appServicePlanId
    httpsOnly: true
    siteConfig: {
      linuxFxVersion: linuxFxVersion
      appCommandLine: 'python src/app.py'
      appSettings: [
        {
          name: 'SCM_DO_BUILD_DURING_DEPLOYMENT'
          value: 'true'
        }
        {
          name: 'WEBSITES_PORT'
          value: '8000'
        }
        {
          name: 'PORT'
          value: '8000'
        }
        {
          name: 'MICROSOFT_APP_ID'
          value: botAppId
        }
        {
          name: 'MICROSOFT_APP_TYPE'
          value: 'MultiTenant'
        }
        {
          name: 'MICROSOFT_APP_PASSWORD'
          value: botAppSecret
        }
        {
          name: 'MICROSOFT_APP_TENANT_ID'
          value: botAppTenantId
        }
        {
          name: 'AZURE_TENANT_ID'
          value: botAppTenantId
        }
        {
          name: 'CONNECTIONS__SERVICE_CONNECTION__SETTINGS__CLIENTID'
          value: botAppId
        }
        {
          name: 'CONNECTIONS__SERVICE_CONNECTION__SETTINGS__CLIENTSECRET'
          value: botAppSecret
        }
        {
          name: 'CONNECTIONS__SERVICE_CONNECTION__SETTINGS__AUTHTYPE'
          value: 'ClientSecret'
        }
        {
          name: 'CONNECTIONS__SERVICE_CONNECTION__SETTINGS__SCOPES'
          value: 'https://api.botframework.com/.default'
        }
        {
          name: 'CONNECTIONS__SERVICE_CONNECTION__SETTINGS__AUTHORITY'
          value: '${environment().authentication.loginEndpoint}${botAppTenantId}'
        }
        {
          name: 'CONNECTIONS__SERVICE_CONNECTION__SETTINGS__TENANTID'
          value: botAppTenantId
        }
        {
          name: 'FOUNDRY_PROJECT_ENDPOINT'
          value: foundryProjectEndpoint
        }
        {
          name: 'FOUNDRY_MODEL_DEPLOYMENT_NAME'
          value: foundryModelDeploymentName
        }
        {
          name: 'FOUNDRY_AGENT_ID'
          value: foundryAgentId
        }
        {
          name: 'FOUNDRY_AGENT_NAME'
          value: foundryAgentName
        }
        {
          name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
          value: appInsights.properties.ConnectionString
        }
      ]
    }
  }
}

resource botService 'Microsoft.BotService/botServices@2022-09-15' = if (deployBot) {
  name: botServiceName
  location: 'global'
  kind: 'azurebot'
  sku: {
    name: 'F0'
  }
  properties: {
    displayName: botServiceName
    endpoint: 'https://${webApp.properties.defaultHostName}/api/messages'
    msaAppId: botAppId
    // Cross-tenant Teams flow (Tenant A users -> Tenant B hosted bot) requires MultiTenant app registration.
    msaAppType: 'MultiTenant'
    msaAppTenantId: botAppTenantId
    msaAppMSIResourceId: ''
  }
}

resource botServiceTeamsChannel 'Microsoft.BotService/botServices/channels@2022-09-15' = if (deployBot) {
  name: 'MsTeamsChannel'
  parent: botService
  location: 'global'
  properties: {
    channelName: 'MsTeamsChannel'
    properties: {
      isEnabled: true
    }
  }
}

output appServiceUrl string = 'https://${webApp.properties.defaultHostName}'
output messagingEndpoint string = 'https://${webApp.properties.defaultHostName}/api/messages'
output botServiceResourceName string = deployBot ? botService.name : ''
output botAppId string = botAppId
output foundryAccountResourceName string = empty(existingFoundryProjectEndpoint) ? foundryAccount.name : ''
output foundryProjectResourceName string = empty(existingFoundryProjectEndpoint) ? foundryProject.name : ''
output foundryProjectEndpoint string = foundryProjectEndpoint
output foundryModelDeploymentName string = foundryModelDeploymentName
