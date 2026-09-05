#!/usr/bin/env bash
set -euo pipefail
tools=$(realpath "${1:?tool directory}")
work=$(realpath "${2:?workspace}")
(cd "$tools"; sha256sum --check --quiet toolchain.sha256)
export JAVA_HOME="$tools/jdk26"
export NON_MODULAR_JAVA_HOME="$tools/jdk8"
export PATH="$tools/maven/bin:$JAVA_HOME/bin:$PATH"
mkdir -p "$HOME/.m2" "$work/eclipse-platform-parent"
cp "$tools/eclipse-platform-parent/pom.xml" "$work/eclipse-platform-parent/pom.xml"
cat > "$HOME/.m2/toolchains.xml" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<toolchains>
  <toolchain><type>jdk</type><provides><id>JavaSE-26</id><version>26</version></provides><configuration><jdkHome>$JAVA_HOME</jdkHome></configuration></toolchain>
  <toolchain><type>jdk</type><provides><id>JavaSE-1.8</id><version>1.8</version></provides><configuration><jdkHome>$NON_MODULAR_JAVA_HOME</jdkHome></configuration></toolchain>
</toolchains>
EOF
# Public Eclipse repositories are needed for Tycho and target-platform snapshots.
# No credentials and no broad repository mirror are introduced.
cat > "$HOME/.m2/settings.xml" <<'EOF'
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0">
  <profiles><profile><id>eclipse-public</id>
    <repositories><repository><id>eclipse</id><url>https://repo.eclipse.org/content/repositories/eclipse/</url><releases><enabled>true</enabled></releases><snapshots><enabled>true</enabled></snapshots></repository></repositories>
    <pluginRepositories><pluginRepository><id>eclipse</id><url>https://repo.eclipse.org/content/repositories/eclipse/</url><releases><enabled>true</enabled></releases><snapshots><enabled>true</enabled></snapshots></pluginRepository></pluginRepositories>
  </profile></profiles><activeProfiles><activeProfile>eclipse-public</activeProfile></activeProfiles>
</settings>
EOF
if [[ -n "${GITHUB_ENV:-}" ]]; then
  printf 'JAVA_HOME=%s\nNON_MODULAR_JAVA_HOME=%s\n' "$JAVA_HOME" "$NON_MODULAR_JAVA_HOME" >> "$GITHUB_ENV"
  printf '%s\n%s\n' "$tools/maven/bin" "$JAVA_HOME/bin" >> "$GITHUB_PATH"
fi
java -version
mvn -version
