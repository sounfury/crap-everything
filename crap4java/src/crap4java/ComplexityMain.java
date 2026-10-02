package crap4java;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

/** 解析源文件清单并输出方法复杂度，不编译目标项目、不运行测试。 */
public final class ComplexityMain {
    private ComplexityMain() {
    }

    /** 入参为 UTF-8 源文件清单路径；输出 CC、起止行、方法名和源文件路径的 TSV。 */
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException("Expected a source file list");
        }
        for (String filename : Files.readAllLines(Path.of(args[0]), StandardCharsets.UTF_8)) {
            Path file = Path.of(filename);
            String source = Files.readString(file, StandardCharsets.UTF_8);
            String className = CrapAnalyzer.classNameFromSource(file, source);
            for (MethodDescriptor method : JavaMethodParser.parse(className, source)) {
                System.out.printf("%d\t%d\t%d\t%s.%s\t%s%n",
                        method.complexity(), method.startLine(), method.endLine(), className, method.name(), file);
            }
        }
    }
}
