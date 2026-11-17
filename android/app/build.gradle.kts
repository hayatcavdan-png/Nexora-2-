plugins { id("com.android.application"); id("org.jetbrains.kotlin.android") }
android {
    namespace = "com.nexora.app"
    compileSdk = 34
    defaultConfig { applicationId = "com.nexora.app"; minSdk = 26; targetSdk = 34; versionCode = 53; versionName = "5.19.0" }
    signingConfigs {
        // Sabit debug anahtarı: her GitHub derlemesi aynı imzayı kullanır, uygulama üzerine güncellenebilir.
        // Yalnızca test (debug) içindir; Play Store / gerçek dağıtım anahtarı ayrı ve gizli tutulmalıdır.
        getByName("debug") {
            storeFile = rootProject.file("nexora-debug.keystore")
            storePassword = "android"; keyAlias = "androiddebugkey"; keyPassword = "android"
        }
    }
    buildTypes {
        // Hızlı, küçültülmüş sürüm (R8). Aynı sabit anahtarla imzalanır: eski sürümün üzerine kurulur.
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
            signingConfig = signingConfigs.getByName("debug")
        }
    }
    compileOptions { sourceCompatibility = JavaVersion.VERSION_17; targetCompatibility = JavaVersion.VERSION_17 }
    kotlinOptions { jvmTarget = "17" }
    buildFeatures { compose = true; buildConfig = true }
    composeOptions { kotlinCompilerExtensionVersion = "1.5.14" }
}
dependencies {
    implementation(platform("androidx.compose:compose-bom:2024.10.01"))
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.material:material-icons-core")
    implementation("androidx.activity:activity-compose:1.9.1")
    implementation("androidx.biometric:biometric:1.1.0")
}
