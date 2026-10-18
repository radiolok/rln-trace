import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import ghidra.program.model.listing.*;
import java.io.*;
public class DumpAll extends GhidraScript {
  public void run() throws Exception {
    String out = getScriptArgs()[0];
    PrintWriter pw = new PrintWriter(new FileWriter(out));
    DecompInterface d = new DecompInterface();
    d.openProgram(currentProgram);
    for (Function f : currentProgram.getFunctionManager().getFunctions(true)) {
      if (f.isExternal() || f.isThunk()) continue;
      DecompileResults r = d.decompileFunction(f, 120, monitor);
      pw.println("// ==== " + f.getName() + " @ " + f.getEntryPoint());
      pw.println(r.decompileCompleted() ? r.getDecompiledFunction().getC() : "// FAILED " + r.getErrorMessage());
    }
    pw.close();
  }
}
