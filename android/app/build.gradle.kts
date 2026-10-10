plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.dictator.ime"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.dictator.ime"
        // 26 and not lower. An InputMethodService works far further back,
        // but the on-device recogniser this build measures is only askable
        // from 33, and anything older would be shipping a keyboard that
        // cannot answer the question this exists to answer.
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = "0.1.0"
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfig = signingConfigs.getByName("debug")
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    sourceSets["main"].java.srcDirs("src/main/kotlin")
}

dependencies {
    implementation("androidx.core:core-ktx:1.15.0")
}
