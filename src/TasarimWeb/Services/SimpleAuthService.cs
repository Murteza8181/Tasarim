using Microsoft.Extensions.Options;

namespace TasarimWeb.Services
{
    public class AuthSettings
    {
        public DefaultUserSettings DefaultUser { get; set; } = new();
    }

    public class DefaultUserSettings
    {
        public string UserName { get; set; } = string.Empty;
        public string Password { get; set; } = string.Empty;
    }

    public interface ISimpleAuthService
    {
        bool ValidateCredentials(string userName, string password);
    }

    public class SimpleAuthService : ISimpleAuthService
    {
        private readonly AuthSettings _settings;

        public SimpleAuthService(IOptions<AuthSettings> options)
        {
            _settings = options.Value;
        }

        public bool ValidateCredentials(string userName, string password)
        {
            if (string.IsNullOrWhiteSpace(_settings.DefaultUser.UserName) ||
                string.IsNullOrWhiteSpace(_settings.DefaultUser.Password))
            {
                return false;
            }

            return string.Equals(userName?.Trim(), _settings.DefaultUser.UserName.Trim(), StringComparison.OrdinalIgnoreCase)
                && password == _settings.DefaultUser.Password;
        }
    }
}
