using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Windows.Forms;

[assembly: AssemblyTitle("AutoClicker Studio Pro - Lanzador")]
[assembly: AssemblyProduct("AutoClicker Studio Pro")]
[assembly: AssemblyVersion("1.0.0.0")]

// Lanzador mínimo: ejecuta main.py con Python en una consola oculta (log en autoclicker.log).
// Con el argumento --debug muestra la consola.
// El manifiesto pide permisos de administrador; el cmd hereda la elevación,
// así que Windows solo muestra un aviso UAC.
static class Launcher
{
    const string Script = "main.py";
    const string LogFile = "autoclicker.log";

    [STAThread]
    static int Main(string[] args)
    {
        bool debug = Array.IndexOf(args, "--debug") >= 0;
        string dir = Path.GetDirectoryName(Application.ExecutablePath);

        if (!File.Exists(Path.Combine(dir, Script)))
        {
            Error("No se encontró " + Script + " junto al lanzador:\n" + dir);
            return 1;
        }

        string python, prefix;
        if (!FindPython(dir, out python, out prefix))
        {
            Error("No se encontró Python.\nInstálalo desde python.org (marca \"Add to PATH\") " +
                  "o crea un entorno .venv dentro de esta carpeta.");
            return 1;
        }

        string cmdLine = "\"" + python + "\" " + prefix + "-u " + Script;
        string inner;
        if (debug)
        {
            // Consola visible; si main.py termina con error, queda abierta para leerlo.
            inner = "title AutoClicker Studio Pro && cd /d \"" + dir + "\" && " + cmdLine + " || pause";
        }
        else
        {
            // Consola oculta; la salida (prints y errores) va a LogFile.
            inner = "cd /d \"" + dir + "\" && " + cmdLine + " > \"" + LogFile + "\" 2>&1";
        }

        ProcessStartInfo psi = new ProcessStartInfo("cmd.exe", "/s /c \"" + inner + "\"");
        psi.WorkingDirectory = dir;
        psi.UseShellExecute = false;
        psi.CreateNoWindow = !debug;

        try
        {
            Process p = Process.Start(psi);
            if (!debug)
            {
                p.WaitForExit();
                if (p.ExitCode != 0)
                {
                    Error("AutoClicker Studio Pro se cerró con un error.\n" +
                          "Revisa el detalle en:\n" + Path.Combine(dir, LogFile));
                    return p.ExitCode;
                }
            }
        }
        catch (Exception ex)
        {
            Error("No se pudo iniciar la aplicación:\n" + ex.Message);
            return 1;
        }
        return 0;
    }

    // Orden: .venv / venv de la carpeta -> py.exe (-3) -> python.exe del PATH.
    static bool FindPython(string dir, out string exe, out string prefix)
    {
        prefix = "";
        string[] locales =
        {
            Path.Combine(dir, @".venv\Scripts\python.exe"),
            Path.Combine(dir, @"venv\Scripts\python.exe")
        };
        foreach (string p in locales)
        {
            if (File.Exists(p)) { exe = p; return true; }
        }

        exe = FindInPath("py.exe");
        if (exe != null) { prefix = "-3 "; return true; }

        exe = FindInPath("python.exe");
        return exe != null;
    }

    static string FindInPath(string file)
    {
        string path = Environment.GetEnvironmentVariable("PATH") ?? "";
        foreach (string part in path.Split(';'))
        {
            string folder = part.Trim().Trim('"');
            if (folder.Length == 0) continue;
            try
            {
                string full = Path.Combine(folder, file);
                if (File.Exists(full)) return full;
            }
            catch (ArgumentException) { }
        }
        return null;
    }

    static void Error(string text)
    {
        MessageBox.Show(text, "AutoClicker Studio Pro", MessageBoxButtons.OK, MessageBoxIcon.Error);
    }
}
