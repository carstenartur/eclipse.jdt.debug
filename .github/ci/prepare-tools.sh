#!/usr/bin/env bash
# Download once; all source variants receive the same archive of tool binaries.
set -euo pipefail
out=$(realpath -m "${1:?tool directory}")
evidence=$(realpath -m "${2:?evidence directory}")
mkdir -p "$out/jdk26" "$out/jdk8" "$out/maven" "$out/eclipse-platform-parent" "$evidence"
url='https://github.com/adoptium/temurin26-binaries/releases/download/jdk-26%2B34-ea-beta/OpenJDK26U-jdk_x64_linux_hotspot_26_34-ea.tar.gz'
curl --fail --location --retry 3 --max-time 240 "$url" -o "$out/jdk26.tar.gz"
curl --fail --location --retry 3 --max-time 60 "$url.sha256.txt" -o "$evidence/jdk26.sha256"
hash=$(awk '{print $1}' "$evidence/jdk26.sha256")
[[ "$hash" =~ ^[a-fA-F0-9]{64}$ ]]
printf '%s  %s\n' "$hash" "$out/jdk26.tar.gz" | sha256sum --check
tar -xzf "$out/jdk26.tar.gz" -C "$out/jdk26" --strip-components=1
rm "$out/jdk26.tar.gz"
"$out/jdk26/bin/java" -XshowSettings:properties -version 2>&1 | tee "$evidence/java26.txt"
grep -Fq 'java.runtime.version = 26-beta+34-ea' "$evidence/java26.txt"
# setup-java supplies one pinned legacy VM. Copy it once for all matrix cells.
cp -a "${JAVA_HOME:?setup-java must first install JDK 8}/." "$out/jdk8/"
"$out/jdk8/bin/java" -version 2>&1 | tee "$evidence/java8.txt"
# BREE compilation uses real libraries for each execution environment, not Java 26 aliases.
for spec in '11 11.0.30 7' '17 17.0.18 8' '21 21.0.10 7'; do
  read -r major version build <<< "$spec"
  url="https://github.com/adoptium/temurin${major}-binaries/releases/download/jdk-${version}%2B${build}/OpenJDK${major}U-jdk_x64_linux_hotspot_${version}_${build}.tar.gz"
  mkdir -p "$out/jdk$major"
  curl --fail --location --retry 3 --max-time 240 "$url" -o "$out/jdk$major.tar.gz"
  curl --fail --location --retry 3 --max-time 60 "$url.sha256.txt" -o "$evidence/jdk$major.sha256"
  hash=$(awk '{print $1}' "$evidence/jdk$major.sha256")
  [[ "$hash" =~ ^[a-fA-F0-9]{64}$ ]]
  printf '%s  %s\n' "$hash" "$out/jdk$major.tar.gz" | sha256sum --check
  tar -xzf "$out/jdk$major.tar.gz" -C "$out/jdk$major" --strip-components=1
  rm "$out/jdk$major.tar.gz"
  "$out/jdk$major/bin/java" -XshowSettings:properties -version 2>&1 | tee "$evidence/java$major.txt"
  grep -Fq "java.runtime.version = $version+$build" "$evidence/java$major.txt"
done
url='https://archive.apache.org/dist/maven/maven-3/3.9.11/binaries/apache-maven-3.9.11-bin.tar.gz'
curl --fail --location --retry 3 --max-time 120 "$url" -o "$out/maven.tar.gz"
curl --fail --location --retry 3 --max-time 60 "$url.sha512" -o "$evidence/maven.sha512"
hash=$(awk '{print $1}' "$evidence/maven.sha512")
[[ "$hash" =~ ^[a-fA-F0-9]{128}$ ]]
printf '%s  %s\n' "$hash" "$out/maven.tar.gz" | sha512sum --check
tar -xzf "$out/maven.tar.gz" -C "$out/maven" --strip-components=1
rm "$out/maven.tar.gz"
# Freeze the parent POM once, rather than resolving a moving SNAPSHOT per cell.
base='https://repo.eclipse.org/content/repositories/eclipse/org/eclipse/eclipse-platform-parent/4.42.0-SNAPSHOT'
curl --fail --location --retry 3 --max-time 90 "$base/maven-metadata.xml" -o "$evidence/parent-metadata.xml"
version=$(python3 - "$evidence/parent-metadata.xml" <<'PY'
import sys, xml.etree.ElementTree as E
root = E.parse(sys.argv[1]).getroot()
values = [v.findtext('value') for v in root.findall('./versioning/snapshotVersions/snapshotVersion')
          if v.findtext('extension') == 'pom' and not v.findtext('classifier')]
if len(values) != 1:
    raise SystemExit('Expected exactly one parent POM snapshot in metadata')
print(values[0])
PY
)
[[ "$version" =~ ^[a-zA-Z0-9._-]+$ ]]
url="$base/eclipse-platform-parent-$version.pom"
curl --fail --location --retry 3 --max-time 90 "$url" -o "$out/eclipse-platform-parent/pom.xml"
printf '%s\n' "$url" > "$evidence/parent-url.txt"
cp "$out/eclipse-platform-parent/pom.xml" "$evidence/parent.pom"
cat > "$evidence/remaining-differences.txt" <<'EOF'
JDK: same OpenJDK feature/build 26+34, but Temurin instead of the Jenkins OpenJDK distribution.
BREE library VMs: real Temurin 8, 11, 17 and 21 installations; exact patches are recorded, not claimed identical to Jenkins.
Maven: pinned 3.9.11 (documented CBI latest); exact Jenkins executable could not be obtained.
Runner: GitHub Ubuntu 24.04, not the Eclipse Kubernetes agent. Display: Xvfb instead of Xvnc.
Parent POM and tool binaries are identical in all cells of this run.
Other SNAPSHOT/p2 dependencies can move. Compare external-dependency-hashes.json before causal attribution.
No test timeout, retry count, port or assertion is relaxed. Raw test failures remain failures.
EOF
(cd "$out"; find jdk26 jdk8 jdk11 jdk17 jdk21 maven eclipse-platform-parent -type f -print0 | sort -z | xargs -0 sha256sum) > "$out/toolchain.sha256"
cp "$out/toolchain.sha256" "$evidence/toolchain.sha256"
cp "$evidence/remaining-differences.txt" "$out/remaining-differences.txt"
