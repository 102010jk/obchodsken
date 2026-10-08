package cz.obchodsken

import android.app.Application
import cz.obchodsken.data.AppDatabase
import cz.obchodsken.data.Repository
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob

class App : Application() {
    /** Scope celé aplikace – hromadný import poběží i při přepínání obrazovek. */
    val appScope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
    val repo: Repository by lazy { Repository(this, AppDatabase.create(this), appScope) }
}
