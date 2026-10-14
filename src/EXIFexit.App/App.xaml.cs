using System.IO;
using System.Text;
using System.Windows;
using System.Windows.Threading;
using EXIFexit.Infrastructure;
using Microsoft.Extensions.DependencyInjection;

namespace EXIFexit.App;

public partial class App : System.Windows.Application
{
    public static IServiceProvider Services { get; private set; } = null!;

    protected override void OnStartup(StartupEventArgs e)
    {
        // Surface crashes instead of silent exit (WinExe has no console).
        DispatcherUnhandledException += OnDispatcherUnhandledException;
        AppDomain.CurrentDomain.UnhandledException += OnDomainUnhandledException;
        TaskScheduler.UnobservedTaskException += OnUnobservedTaskException;

        try
        {
            base.OnStartup(e);

            var contentRoot = FindContentRoot();
            var sc = new ServiceCollection();
            sc.AddExifExit(contentRoot);
            sc.AddSingleton<MainViewModel>();
            sc.AddSingleton<MainWindow>();
            Services = sc.BuildServiceProvider();
        }
        catch (Exception ex)
        {
            ShowFatal(ex, "Startup failed");
            Shutdown(1);
        }
    }

    private void OnDispatcherUnhandledException(object sender, DispatcherUnhandledExceptionEventArgs e)
    {
        ShowFatal(e.Exception, "Unhandled UI exception");
        e.Handled = true;
        Shutdown(1);
    }

    private static void OnDomainUnhandledException(object? sender, UnhandledExceptionEventArgs e)
    {
        if (e.ExceptionObject is Exception ex)
            ShowFatal(ex, "Unhandled exception");
    }

    private static void OnUnobservedTaskException(object? sender, UnobservedTaskExceptionEventArgs e)
    {
        ShowFatal(e.Exception, "Background task exception");
        e.SetObserved();
    }

    private static void ShowFatal(Exception ex, string title)
    {
        try
        {
            var sb = new StringBuilder();
            sb.AppendLine(title);
            sb.AppendLine();
            sb.AppendLine(ex.ToString());

            var logDir = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "EXIFexit");
            Directory.CreateDirectory(logDir);
            var logPath = Path.Combine(logDir, "crash.log");
            File.WriteAllText(logPath, sb.ToString());

            MessageBox.Show(
                $"{ex.Message}\n\nDetails written to:\n{logPath}",
                "EXIFexit — " + title,
                MessageBoxButton.OK,
                MessageBoxImage.Error);
        }
        catch
        {
            // last resort
            try
            {
                MessageBox.Show(ex.Message, "EXIFexit error", MessageBoxButton.OK, MessageBoxImage.Error);
            }
            catch
            {
                // ignore
            }
        }
    }

    private static string FindContentRoot()
    {
        // Single-file publish extracts to a temp dir; also look next to the original EXE.
        var candidates = new List<string>();

        try
        {
            var processPath = Environment.ProcessPath;
            if (!string.IsNullOrEmpty(processPath))
                candidates.Add(Path.GetDirectoryName(processPath)!);
        }
        catch
        {
            // ignore
        }

        candidates.Add(AppContext.BaseDirectory);

        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        for (var i = 0; i < 8 && dir != null; i++)
        {
            candidates.Add(dir.FullName);
            dir = dir.Parent;
        }

        foreach (var root in candidates.Distinct(StringComparer.OrdinalIgnoreCase))
        {
            var candidate = Path.Combine(root, "data", "masks", "core.json");
            if (File.Exists(candidate))
                return root;
        }

        return AppContext.BaseDirectory;
    }
}
