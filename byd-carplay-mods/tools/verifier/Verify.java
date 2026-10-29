import org.jf.dexlib2.DexFileFactory;
import org.jf.dexlib2.Opcodes;
import org.jf.dexlib2.analysis.AnalysisException;
import org.jf.dexlib2.analysis.ClassPath;
import org.jf.dexlib2.analysis.ClassProvider;
import org.jf.dexlib2.analysis.DexClassProvider;
import org.jf.dexlib2.analysis.MethodAnalyzer;
import org.jf.dexlib2.dexbacked.DexBackedDexFile;
import org.jf.dexlib2.iface.ClassDef;
import org.jf.dexlib2.iface.Method;
import org.jf.dexlib2.iface.MultiDexContainer;
import org.jf.dexlib2.Opcode;
import org.jf.dexlib2.analysis.AnalyzedInstruction;
import org.jf.dexlib2.analysis.RegisterType;
import org.jf.dexlib2.iface.instruction.FiveRegisterInstruction;
import org.jf.dexlib2.iface.instruction.Instruction;
import org.jf.dexlib2.iface.instruction.OneRegisterInstruction;
import org.jf.dexlib2.iface.instruction.ReferenceInstruction;
import org.jf.dexlib2.iface.instruction.RegisterRangeInstruction;
import org.jf.dexlib2.iface.instruction.ThreeRegisterInstruction;
import org.jf.dexlib2.iface.instruction.TwoRegisterInstruction;
import org.jf.dexlib2.iface.reference.FieldReference;
import org.jf.dexlib2.iface.reference.MethodReference;

import java.io.File;
import java.io.PrintWriter;
import java.util.ArrayList;
import java.util.List;
import java.util.TreeSet;

/**
 * Register-type verification of every method in an APK's dex files (the class of bug that crashed the first
 * mod with "VerifyError: Verifier rejected class"). Usage: Verify <apk> <frameworkDex|-> <report.txt>
 * Each finding is one line: CLASS->method | message. Messages about classes that are not on the (partial)
 * framework class path are written with the prefix UNRESOLVED and are not real findings.
 */
public class Verify {
    public static void main(String[] a) throws Exception {
        File apk = new File(a[0]);
        Opcodes ops = Opcodes.forApi(29);
        MultiDexContainer<? extends DexBackedDexFile> container = DexFileFactory.loadDexContainer(apk, ops);
        List<ClassProvider> providers = new ArrayList<ClassProvider>();
        List<DexBackedDexFile> dexes = new ArrayList<DexBackedDexFile>();
        for (String name : container.getDexEntryNames()) {
            DexBackedDexFile d = container.getEntry(name).getDexFile();
            dexes.add(d);
            providers.add(new DexClassProvider(d));
        }
        if (!"-".equals(a[1])) {
            providers.add(new DexClassProvider(DexFileFactory.loadDexFile(new File(a[1]), ops)));
        }
        ClassPath cp = new ClassPath(providers, true, ClassPath.NOT_ART);
        TreeSet<String> real = new TreeSet<String>();
        int methods = 0, unresolved = 0;
        for (DexBackedDexFile d : dexes) {
            for (ClassDef c : d.getClasses()) {
                for (Method m : c.getMethods()) {
                    if (m.getImplementation() == null) continue;
                    methods++;
                    String id = c.getType() + "->" + m.getName() + "(";
                    StringBuilder sig = new StringBuilder();
                    for (CharSequence p : m.getParameterTypes()) sig.append(p);
                    id += sig + ")" + m.getReturnType();
                    try {
                        MethodAnalyzer an = new MethodAnalyzer(cp, m, null, false);
                        AnalysisException ex = an.getAnalysisException();
                        if (ex == null) strict(an, m, id, real);
                        if (ex != null) {
                            String msg = String.valueOf(ex.getMessage());
                            Throwable cause = ex.getCause();
                            String all = msg + " " + (cause == null ? "" : cause.getClass().getSimpleName() + " " + cause.getMessage());
                            if (all.contains("UnresolvedClass") || all.contains("Could not resolve")) {
                                unresolved++;
                            } else {
                                real.add(id + " | " + msg.replace('\n', ' ') + " @0x" + Integer.toHexString(ex.codeAddress));
                            }
                        }
                    } catch (Throwable t) {
                        String s = String.valueOf(t.getMessage());
                        if (t.getClass().getSimpleName().contains("Unresolved") || s.contains("Could not resolve")) unresolved++;
                        else real.add(id + " | " + t.getClass().getSimpleName() + ": " + s.replace('\n', ' '));
                    }
                }
            }
        }
        PrintWriter w = new PrintWriter(a[2], "UTF-8");
        for (String s : real) w.println(s);
        w.close();
        System.out.println("methods analysed: " + methods + ", unresolved-class skips: " + unresolved + ", findings: " + real.size());
    }

    // ---- strict register-type rules (what ART's verifier rejects) ----

    static boolean isRef(int c) {
        return c == RegisterType.NULL || c == RegisterType.REFERENCE || c == RegisterType.UNINIT_REF || c == RegisterType.UNINIT_THIS;
    }

    static boolean isIntLike(int c) {
        return c == RegisterType.NULL || c == RegisterType.ONE || c == RegisterType.BOOLEAN || c == RegisterType.BYTE
                || c == RegisterType.POS_BYTE || c == RegisterType.SHORT || c == RegisterType.POS_SHORT
                || c == RegisterType.CHAR || c == RegisterType.INTEGER || c == RegisterType.FLOAT;
    }

    static boolean isWide(int c) {
        return c == RegisterType.LONG_LO || c == RegisterType.DOUBLE_LO;
    }

    static String catName(int c) {
        String[] n = {"Unknown", "Uninit", "Null", "One", "Boolean", "Byte", "PosByte", "Short", "PosShort", "Char", "Integer",
                "Float", "LongLo", "LongHi", "DoubleLo", "DoubleHi", "UninitRef", "UninitThis", "Reference", "Conflicted"};
        return c >= 0 && c < n.length ? n[c] : String.valueOf(c);
    }

    /** kind: 'R' reference, 'I' int-like, 'W' wide, 'A' any defined value. */
    static void need(AnalyzedInstruction ai, int reg, char kind, MethodAnalyzer an, String id, Opcode op, String why,
                     java.util.Set<String> out) {
        int c;
        try {
            c = ai.getPreInstructionRegisterType(reg).category;
        } catch (Throwable t) {
            return;
        }
        boolean ok;
        switch (kind) {
            case 'R': ok = isRef(c); break;
            case 'I': ok = isIntLike(c); break;
            case 'W': ok = isWide(c); break;
            default: ok = c != RegisterType.UNKNOWN && c != RegisterType.CONFLICTED && c != RegisterType.UNINIT; break;
        }
        if (c == RegisterType.UNKNOWN || c == RegisterType.CONFLICTED) ok = false;
        if (!ok) {
            out.add(id + " | @0x" + Integer.toHexString(an.getInstructionAddress(ai)) + " " + op.name + " v" + reg + " is "
                    + catName(c) + ", " + why);
        }
    }

    static char kindOf(CharSequence type) {
        char ch = type.charAt(0);
        if (ch == 'L' || ch == '[') return 'R';
        if (ch == 'J' || ch == 'D') return 'W';
        return 'I';
    }

    static void strict(MethodAnalyzer an, Method m, String id, java.util.Set<String> out) {
        List<AnalyzedInstruction> list = an.getAnalyzedInstructions();
        boolean isStatic = org.jf.dexlib2.AccessFlags.STATIC.isSet(m.getAccessFlags());
        for (AnalyzedInstruction ai : list) {
            if (ai.getPredecessorCount() == 0 && !ai.isBeginningInstruction()) continue;   // unreachable: not verified
            Instruction ins = ai.getInstruction();
            Opcode op = ins.getOpcode();
            String n = op.name;
            boolean sets = op.setsRegister();
            boolean twoAddr = n.endsWith("/2addr");
            // ---- invokes and filled-new-array: arguments by signature ----
            if (ins instanceof FiveRegisterInstruction || ins instanceof RegisterRangeInstruction) {
                int[] regs;
                if (ins instanceof FiveRegisterInstruction) {
                    FiveRegisterInstruction f = (FiveRegisterInstruction) ins;
                    int[] all = {f.getRegisterC(), f.getRegisterD(), f.getRegisterE(), f.getRegisterF(), f.getRegisterG()};
                    regs = java.util.Arrays.copyOf(all, f.getRegisterCount());
                } else {
                    RegisterRangeInstruction r = (RegisterRangeInstruction) ins;
                    regs = new int[r.getRegisterCount()];
                    for (int i = 0; i < regs.length; i++) regs[i] = r.getStartRegister() + i;
                }
                if (n.startsWith("invoke") && ins instanceof ReferenceInstruction
                        && ((ReferenceInstruction) ins).getReference() instanceof MethodReference) {
                    MethodReference mr = (MethodReference) ((ReferenceInstruction) ins).getReference();
                    int k = 0;
                    if (!n.startsWith("invoke-static")) {
                        if (k < regs.length) need(ai, regs[k], 'R', an, id, op, "receiver must be an object", out);
                        k++;
                    }
                    for (CharSequence p : mr.getParameterTypes()) {
                        char kind = kindOf(p);
                        if (k >= regs.length) break;
                        need(ai, regs[k], kind, an, id, op, "argument " + p + " of " + mr.getName() + " has the wrong kind", out);
                        k += kind == 'W' ? 2 : 1;
                    }
                } else {
                    for (int r : regs) need(ai, r, 'A', an, id, op, "register is not set", out);
                }
                continue;
            }
            if (!(ins instanceof OneRegisterInstruction)) continue;
            int a = ((OneRegisterInstruction) ins).getRegisterA();
            boolean readsA = !sets || twoAddr || n.equals("check-cast");
            Integer b = ins instanceof TwoRegisterInstruction ? Integer.valueOf(((TwoRegisterInstruction) ins).getRegisterB()) : null;
            Integer c = ins instanceof ThreeRegisterInstruction ? Integer.valueOf(((ThreeRegisterInstruction) ins).getRegisterC()) : null;
            // generic: every register read must hold a defined value
            if (readsA) need(ai, a, 'A', an, id, op, "register is not set", out);
            if (b != null) need(ai, b.intValue(), 'A', an, id, op, "register is not set", out);
            if (c != null) need(ai, c.intValue(), 'A', an, id, op, "register is not set", out);
            // specific kinds
            if (n.equals("return-object")) need(ai, a, 'R', an, id, op, "must return an object", out);
            else if (n.equals("return")) need(ai, a, 'I', an, id, op, "must return a number", out);
            else if (n.equals("return-wide")) need(ai, a, 'W', an, id, op, "must return a long/double", out);
            else if (n.equals("throw") || n.startsWith("monitor-")) need(ai, a, 'R', an, id, op, "must be an object", out);
            else if (n.equals("check-cast")) need(ai, a, 'R', an, id, op, "must be an object", out);
            else if (n.equals("instance-of") && b != null) need(ai, b.intValue(), 'R', an, id, op, "must be an object", out);
            else if (n.equals("array-length") && b != null) need(ai, b.intValue(), 'R', an, id, op, "must be an array", out);
            else if (n.equals("move-object") || n.equals("move-object/from16") || n.equals("move-object/16")) {
                if (b != null) need(ai, b.intValue(), 'R', an, id, op, "must be an object", out);
            } else if (n.equals("move") || n.equals("move/from16") || n.equals("move/16")) {
                if (b != null) need(ai, b.intValue(), 'I', an, id, op, "must be a number", out);
            } else if (n.equals("new-array") && b != null) need(ai, b.intValue(), 'I', an, id, op, "size must be a number", out);
            else if ((n.startsWith("aget") || n.startsWith("aput")) && b != null && c != null) {
                need(ai, b.intValue(), 'R', an, id, op, "array must be an object", out);
                need(ai, c.intValue(), 'I', an, id, op, "index must be a number", out);
                if (n.equals("aput-object")) need(ai, a, 'R', an, id, op, "must be an object", out);
            } else if ((n.startsWith("iget") || n.startsWith("iput")) && b != null) {
                need(ai, b.intValue(), 'R', an, id, op, "instance must be an object", out);
                if (n.startsWith("iput") && ins instanceof ReferenceInstruction
                        && ((ReferenceInstruction) ins).getReference() instanceof FieldReference) {
                    need(ai, a, kindOf(((FieldReference) ((ReferenceInstruction) ins).getReference()).getType()), an, id, op,
                            "value does not match the field type", out);
                }
            } else if (n.startsWith("sput") && ins instanceof ReferenceInstruction
                    && ((ReferenceInstruction) ins).getReference() instanceof FieldReference) {
                need(ai, a, kindOf(((FieldReference) ((ReferenceInstruction) ins).getReference()).getType()), an, id, op,
                        "value does not match the field type", out);
            } else if (n.startsWith("if-") && !n.startsWith("if-eq") && !n.startsWith("if-ne")) {
                need(ai, a, 'I', an, id, op, "must be a number", out);
                if (b != null) need(ai, b.intValue(), 'I', an, id, op, "must be a number", out);
            } else if (n.contains("-int") || n.contains("int-to-") || n.contains("-long") || n.contains("-float")
                    || n.contains("-double") || n.startsWith("neg-") || n.startsWith("not-")) {
                // arithmetic never takes an object
                if (readsA) failIfRef(ai, a, an, id, op, out);
                if (b != null) failIfRef(ai, b.intValue(), an, id, op, out);
                if (c != null) failIfRef(ai, c.intValue(), an, id, op, out);
            }
        }
    }

    static void failIfRef(AnalyzedInstruction ai, int reg, MethodAnalyzer an, String id, Opcode op, java.util.Set<String> out) {
        int cat = ai.getPreInstructionRegisterType(reg).category;
        if (cat == RegisterType.REFERENCE || cat == RegisterType.UNINIT_REF) {
            out.add(id + " | @0x" + Integer.toHexString(an.getInstructionAddress(ai)) + " " + op.name + " v" + reg
                    + " is an object but arithmetic needs a number");
        }
    }
}
