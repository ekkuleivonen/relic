package config

import "github.com/ekkuleivonen/relic/packages/auth"

func (c Config) AuthServiceConfig() auth.Config {
	return auth.Config{
		SuperuserEmail:    c.SuperuserEmail,
		SuperuserPassword: c.SuperuserPassword,
		SessionTTL:        c.SessionTTL,
		SessionSecret:     c.SessionSecret,
		SecureCookies:     c.SecureCookies(),
		WebAppURL:         c.WebAppURL,
		OIDC: auth.OIDCConfig{
			IssuerURL:    c.OIDCIssuerURL,
			ClientID:     c.OIDCClientID,
			ClientSecret: c.OIDCClientSecret,
			RedirectURL:  c.OIDCRedirectURL,
		},
	}
}
