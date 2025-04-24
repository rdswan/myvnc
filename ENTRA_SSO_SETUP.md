# Microsoft Entra ID SSO Setup for VNC Manager

This document outlines the steps to configure Single Sign-On (SSO) for the VNC Manager application using Microsoft Entra ID (formerly Azure Active Directory).

## 1. Register an Application in Entra ID

1. Sign in to the [Azure Portal](https://portal.azure.com/) with an admin account.
2. Navigate to **Microsoft Entra ID** (or Azure Active Directory).
3. Select **App registrations** from the left menu and click **New registration**.
4. Enter the following information:
   - **Name**: VNC Manager
   - **Supported account types**: Accounts in this organizational directory only
   - **Redirect URI**: Web - `http://your-server-address:8000/auth/callback`
5. Click **Register**.

## 2. Configure Authentication

1. In your newly registered app, go to **Authentication**.
2. Under **Implicit grant and hybrid flows**, check **ID tokens**.
3. Under **Advanced settings**, set **Allow public client flows** to **No**.
4. Click **Save**.

## 3. Create Client Secret

1. Go to **Certificates & secrets**.
2. Click **New client secret**.
3. Enter a description and select an expiration period.
4. Click **Add**.
5. **IMPORTANT**: Copy the generated secret value immediately. You won't be able to see it again.

## 4. Configure API Permissions

1. Go to **API permissions**.
2. Click **Add a permission**.
3. Select **Microsoft Graph**.
4. Select **Delegated permissions**.
5. Add the following permissions:
   - `User.Read` (to read user profile)
   - `Directory.Read.All` (to read group memberships)
6. Click **Add permissions**.
7. Click **Grant admin consent for [your organization]**.

## 5. Configure VNC Manager

1. Note your application's **Application (client) ID** and **Directory (tenant) ID** from the overview page.
2. Set the following environment variables on your VNC Manager server:
   ```bash
   export AUTH_METHOD="entra"
   export ENTRA_TENANT_ID="your-tenant-id"  # From step 1
   export ENTRA_CLIENT_ID="your-client-id"  # From step 1
   export ENTRA_CLIENT_SECRET="your-client-secret"  # From step 3
   export ENTRA_REDIRECT_URI="http://your-server-address:8000/auth/callback"  # Same as in step 1
   ```

3. Alternatively, you can update the `setup_entra.sh` script with your credentials.

## 6. Restart VNC Manager

```bash
./setup_entra.sh
```

## Troubleshooting

- Check application logs for authentication errors
- Verify that redirect URIs match exactly between Azure portal and application config
- Ensure that all required permissions have been granted
- For password authentication issues, ensure the tenant allows Resource Owner Password Credentials flow

## Security Notes

- Store client secrets securely, preferably using a secrets management solution
- Rotate client secrets regularly
- Consider using certificate-based authentication instead of client secrets for production deployments 